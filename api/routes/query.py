"""
Query Routes - Main query endpoint for streaming responses
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from datetime import datetime
import json
import uuid
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.schemas.models import QueryRequest
from api.sessions import get_or_create_session, is_session_rate_limited
from api.logging import save_question_response, contains_medical_disclaimer
from api.query_chromadb import ask_question_stream

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/query")
@limiter.limit("10/hour")  # Max 10 questions per hour per IP
async def query_agent(request: Request, query_request: QueryRequest):
    """
    Main endpoint to ask questions to the agent and receive streaming responses
    """
    client_ip = get_remote_address(request)
    print(
        f"[DEBUG][route:/query] incoming request ip={client_ip} session_id={query_request.session_id} lang={query_request.language}",
        flush=True,
    )

    # Check session-based rate limiting
    if query_request.session_id and is_session_rate_limited(query_request.session_id):
        print(f"[DEBUG][route:/query] rate_limited session_id={query_request.session_id}", flush=True)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": "Trop de requêtes. Veuillez patienter quelques instants."
            }
        )
    
    session_id, session = get_or_create_session(query_request.session_id)
    
    conversation_history = session['messages']
    user_message = {
        'role': 'user',
        'content': query_request.question,
        'timestamp': datetime.now().isoformat()
    }
    conversation_history.append(user_message)
    
    question_id = str(uuid.uuid4())
    print(
        f"[DEBUG][route:/query] assigned session_id={session_id} question_id={question_id} history_size={len(conversation_history)}",
        flush=True,
    )
    
    def generate():
        # Generate the assistant's streaming response (SSE)
        try:
            print(f"[DEBUG][route:/query] stream_start question_id={question_id}", flush=True)
            yield f"data: {json.dumps({'session_id': session_id, 'question_id': question_id, 'chunk': ''})}\n\n"
            
            assistant_response = ""
            is_refusal = False
            chunk_count = 0
            
            for chunk in ask_question_stream(
                query_request.question,
                language=query_request.language,
                timezone=query_request.timezone,
                locale=query_request.locale,
                conversation_history=conversation_history,
                session=session,
                question_id=question_id,
                agent=query_request.agent
            ):
                # Detect refusal marker
                if chunk == "__REFUSAL__":
                    is_refusal = True
                    print(f"[DEBUG][route:/query] refusal_marker question_id={question_id}", flush=True)
                    continue  # Don't include marker in response
                
                chunk_count += 1
                assistant_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            # Save question and response to log (including refused ones)
            save_question_response(question_id, query_request.question, assistant_response)
            
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
            print(
                f"[DEBUG][route:/query] stream_done question_id={question_id} chunks={chunk_count} answer_len={len(assistant_response)} links_count={len(links)} refused={is_refusal}",
                flush=True,
            )
            yield f"data: {json.dumps({'links': links})}\n\n"
            
            # Send completion marker
            yield f"data: [DONE]\n\n"
            
        except Exception as e:
            # Handle any errors during streaming
            error_message = f"Error during streaming: {str(e)}"
            print(f"[DEBUG][route:/query] EXCEPTION question_id={question_id} error={error_message}", flush=True)
            yield f"data: {json.dumps({'error': error_message})}\n\n"
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
