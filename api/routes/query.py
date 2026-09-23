"""
Query Routes - Main query endpoint for streaming responses
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from datetime import datetime
import json
import uuid
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.schemas.models import QueryRequest
from api.services.entra_auth_service import require_admin, require_client_or_query_key
from api.services.sessions import get_or_create_session, is_session_rate_limited
from api.services.logging import save_question_response, contains_medical_disclaimer
from api.services.generated_questions_loader import load_generated_questions
from api.services.query_chromadb import ask_question_stream, get_debug_local_kb_root_folder
import api.services.config as config_service

router = APIRouter(dependencies=[Depends(require_client_or_query_key)])
limiter = Limiter(key_func=get_remote_address)


def _resolve_requested_model(request: Request, query_request: QueryRequest) -> str | None:
    body_model = (query_request.llm_model or "").strip()
    if body_model:
        return body_model

    header_model = (request.headers.get("x-selected-model") or "").strip()
    return header_model or None


def _resolve_runtime_provider_and_model(
    request: Request,
    query_request: QueryRequest,
    *,
    debug_mode: bool,
) -> tuple[str | None, str | None]:
    prefix = "DEBUG" if debug_mode else "PROD"

    try:
        config_service.load_prod_config(force_reload=False)
    except Exception:
        pass

    config_values = config_service._GLOBAL_PROD_CONFIG
    provider = str(config_values.get(f"{prefix}_PROVIDER", "") or "").strip().lower() or None
    saved_model = str(config_values.get(f"{prefix}_LLM", "") or "").strip() or None
    requested_model = _resolve_requested_model(request, query_request)

    # Debug mode: always prefer the model selected by the user.
    # Prod mode: always prefer the model saved in global config.
    if debug_mode:
        model = requested_model or saved_model
    else:
        model = saved_model or requested_model

    return provider, model


def _resolve_runtime_chroma_path(*, debug_mode: bool, chroma_db_path: str | None) -> str | None:
    def _normalize_chroma_path(value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        if not normalized:
            return normalized
        if normalized.startswith("nutrifaq-dbase-main/"):
            return normalized
        if normalized.startswith("chroma_db_") and "/" not in normalized:
            return f"nutrifaq-dbase-main/{normalized}"
        if "/" not in normalized:
            return f"nutrifaq-dbase-main/{normalized}"
        return normalized

    if chroma_db_path and chroma_db_path.strip():
        return _normalize_chroma_path(chroma_db_path)

    prefix = "DEBUG" if debug_mode else "PROD"

    try:
        config_service.load_prod_config(force_reload=False)
    except Exception:
        pass

    config_values = config_service._GLOBAL_PROD_CONFIG
    configured_path = (
        config_values.get(f"{prefix}_SQLITE")
        or config_values.get(f"{prefix}_CHROMA_DB_PATH")
        or ""
    )
    configured_path = str(configured_path).strip()
    if not configured_path:
        return None
    return _normalize_chroma_path(configured_path)


def _query_agent_response(
    request: Request,
    query_request: QueryRequest,
    *,
    debug_mode: bool = False,
    chroma_db_path: str | None = None,
):
    """Shared streaming response builder for /query and /query_debug."""
    # Rate-limit enforcement disabled temporarily.
    # if query_request.session_id and is_session_rate_limited(query_request.session_id):
    #     return JSONResponse(
    #         status_code=429,
    #         content={
    #             "error": "Rate limit exceeded",
    #             "message": "Trop de requêtes. Veuillez patienter quelques instants."
    #         }
    #     )

    session_id, session = get_or_create_session(query_request.session_id)

    conversation_history = session['messages']
    user_message = {
        'role': 'user',
        'content': query_request.question,
        'timestamp': datetime.now().isoformat()
    }
    conversation_history.append(user_message)

    question_id = str(uuid.uuid4())

    def generate():
        # Generate the assistant's streaming response (SSE)
        try:
            yield f"data: {json.dumps({'session_id': session_id, 'question_id': question_id, 'chunk': ''})}\n\n"

            assistant_response = ""
            is_refusal = False
            provider_name, selected_model = _resolve_runtime_provider_and_model(
                request,
                query_request,
                debug_mode=debug_mode,
            )
            resolved_chroma_path = _resolve_runtime_chroma_path(
                debug_mode=debug_mode,
                chroma_db_path=chroma_db_path,
            )

            for chunk in ask_question_stream(
                query_request.question,
                language=query_request.language,
                timezone=query_request.timezone,
                locale=query_request.locale,
                llm_model=selected_model,
                llm_provider=provider_name,
                kb_root_folder=(get_debug_local_kb_root_folder() if debug_mode else None),
                chroma_db_path=resolved_chroma_path,
                conversation_history=conversation_history,
                session=session,
                question_id=question_id,
                agent=query_request.agent
            ):
                # Detect refusal marker
                if chunk == "__REFUSAL__":
                    is_refusal = True
                    continue  # Don't include marker in response

                assistant_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            # Save question and response to log (including refused ones)
            save_question_response(question_id, query_request.question, assistant_response, model_used=selected_model)

            # Check if response contains medical disclaimer (don't show links)
            has_medical_disclaimer = contains_medical_disclaimer(assistant_response)

            # Mark refusal or medical disclaimer in session for links endpoint
            if is_refusal or has_medical_disclaimer:
                session.setdefault('refusals', set()).add(question_id)

            # Only add to history if not a refusal
            if not is_refusal:
                assistant_message = {
                    'role': 'assistant',
                    'content': assistant_response,
                    'timestamp': datetime.now().isoformat()
                }
                conversation_history.append(assistant_message)
            else:
                # Remove the user message from history since it was refused
                conversation_history.pop()

            # Send links as final SSE event (empty if refusal or medical disclaimer)
            links = session['links'].get(question_id, []) if not (is_refusal or has_medical_disclaimer) else []
            yield f"data: {json.dumps({'links': links})}\n\n"

            # Send completion marker
            yield f"data: [DONE]\n\n"

        except Exception as e:
            # Handle any errors during streaming without exposing raw backend strings.
            # The frontend translates the error key locally based on the active language.
            error_message = str(e) or "Error during streaming"
            yield f"data: {json.dumps({'error_key': 'messages.error', 'error': error_message})}\n\n"
            yield f"data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@router.post("/query")
# @limiter.limit("10/hour")  # Max 10 questions per hour per IP
async def query_agent(request: Request, query_request: QueryRequest, chroma_db_path: str | None = None):
    """
    Main endpoint to ask questions to the agent and receive streaming responses
    """
    return _query_agent_response(request, query_request, debug_mode=False, chroma_db_path=chroma_db_path)


@router.post("/query_debug", dependencies=[Depends(require_admin)])
# @limiter.limit("10/hour")
async def query_agent_debug(request: Request, query_request: QueryRequest, chroma_db_path: str | None = None):
    """Admin-only debug query endpoint using the debug knowledge-base root."""
    return _query_agent_response(request, query_request, debug_mode=True, chroma_db_path=chroma_db_path)


@router.get("/api/generated-questions")
async def list_generated_questions():
    """Return generated questions grouped by document title from local debug KB."""
    try:
        payload = load_generated_questions()
        return {
            "status": "ok",
            **payload,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Unable to read generated questions: {exc}",
            },
        )
