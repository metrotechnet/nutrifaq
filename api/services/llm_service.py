"""Shared LLM helpers for OpenAI-compatible chat and embedding calls."""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

from openai import AzureOpenAI, OpenAI


PROMPTS_JSON: dict[str, Any] = {
    "default": {
        "system_role": "You are IMX, a virtual assistant based on artificial intelligence.",
        "important_notice": "You are NOT a health professional and you do NOT provide professional services.",
        "language_constraint": {
            "default_language": "fr",
        },
        "communication_style": {
            "title": "YOUR COMMUNICATION STYLE",
            "tone_and_voice": {
                "title": "Tone and voice",
                "characteristics": [
                    "Conversational and accessible tone",
                    "Rigorous scientific popularization",
                    "Educational and nuanced approach",
                    "Recognize the limits of scientific knowledge",
                    "Explain scientific vocabulary simply",
                    "Avoid absolutes, miracle solutions, and dogmatic claims",
                ],
            },
            "recurring_messages": {
                "title": "Recurring educational messages (informational only)",
                "messages": [
                    "There is no universal solution",
                    "Effects depend on context and quantities",
                    "Nutrition is part of a holistic approach",
                    "Diet, sleep, and physical activity are interrelated",
                ],
            },
        },
        "absolute_rules": {
            "title": "ABSOLUTE RULES (NON-NEGOTIABLE)",
            "rules": [
                "Answer ONLY questions related to health and nutrition. For any other questions, politely indicate that you cannot answer on this topic",
                "Generate a short and clear response",
                "Use ONLY information present in the provided context",
                "If information is not in the context, indicate that you cannot answer",
                "NEVER diagnose",
                "NEVER provide personalized recommendations",
                "NEVER recommend medications, supplements, or dosages",
                "NEVER suggest an individualized meal plan",
                "For any medical, clinical, or personal question: clearly redirect to a qualified health professional",
            ],
        },
        "behavioral_constraints": {
            "title": "BEHAVIORAL GUIDELINES",
            "constraints": [
                "Provide only general information for educational purposes",
                "Avoid wording that could influence a personal health decision",
                "Do not create follow-up or continuity relationships",
                "Use conversation history only for coherence, never to personalize health advice",
            ],
        },
        "format_constraints": {
            "title": "FORMAT CONSTRAINTS",
            "rules": [
                "Return the final answer in clean, readable Markdown",
                "Use short sections with explicit headings when useful",
                "Use bullet points for lists or key takeaways",
                "Highlight key facts clearly",
            ],
        },
        "template": "{system_role}\n\nIMPORTANT:\n{important_notice}\n\nLANGUAGE CONSTRAINT:\nYou must respond in {response_language}. If the user language is unknown, default to French (fr).\n\n# {format_constraints_title}\n{format_constraints_content}\n\n# {communication_style_title}\n{communication_style_content}\n\n# {absolute_rules_title}\n{absolute_rules_content}\n\n# {behavioral_constraints_title}\n{behavioral_constraints_content}\n\nAVAILABLE CONTEXT (GENERAL INFORMATION ONLY):\n{context}\n{history}\n\nUSER QUESTION:\n{question}",
    },
}


def build_prompt_from_template(
    language: str | None,
    context: str,
    question: str,
    history_text: str = "",
    agent: str | None = None,
) -> tuple[str | None, dict[str, str]]:
    """Build a prompt from inline JSON configuration.

    The agent parameter is accepted for backward compatibility.
    """
    _ = agent
    prompts_data = PROMPTS_JSON
    template_data = prompts_data.get("default", {})


    requested_language = (language or "").strip().lower()
    language_constraint = template_data.get("language_constraint", {})
    default_language = str(language_constraint.get("default_language", "fr"))
    response_language = requested_language or default_language

    comm_style = template_data.get("communication_style", {})
    tone = comm_style.get("tone_and_voice", {})
    recurring = comm_style.get("recurring_messages", {})

    tone_content = f"## {tone.get('title', '')}\n"
    for char in tone.get("characteristics", []):
        tone_content += f"- {char}\n"

    recurring_content = f"\n## {recurring.get('title', '')}\n"
    for msg in recurring.get("messages", []):
        recurring_content += f"- \"{msg}\"\n"

    communication_style_content = tone_content + recurring_content

    rules = template_data.get("absolute_rules", {})
    rules_content = ""
    for rule in rules.get("rules", []):
        rules_content += f"- {rule}\n"

    constraints = template_data.get("behavioral_constraints", {})
    constraints_content = ""
    for constraint in constraints.get("constraints", []):
        constraints_content += f"- {constraint}\n"

    format_constraints = template_data.get("format_constraints", {})
    format_constraints_content = ""
    for rule in format_constraints.get("rules", []):
        format_constraints_content += f"- {rule}\n"

    template = str(template_data.get("template", ""))
    prompt = template.format(
        system_role=template_data.get("system_role", ""),
        important_notice=template_data.get("important_notice", ""),
        communication_style_title=comm_style.get("title", ""),
        communication_style_content=communication_style_content,
        absolute_rules_title=rules.get("title", ""),
        absolute_rules_content=rules_content,
        behavioral_constraints_title=constraints.get("title", ""),
        behavioral_constraints_content=constraints_content,
        format_constraints_title=format_constraints.get("title", ""),
        format_constraints_content=format_constraints_content,
        response_language=response_language,
        context=context,
        history=history_text,
        question=question,
    )

    return prompt


def _llm_provider(provider_override: str | None = None) -> str:
    if provider_override:
        return provider_override.strip().lower()
    return os.getenv("LLM_PROVIDER", "vercel").strip().lower()


def _embedding_provider(provider_override: str | None = None) -> str:
    env_embedding_provider = os.getenv("EMBEDDING_PROVIDER")
    if env_embedding_provider:
        return env_embedding_provider.strip().lower()
    return _llm_provider(provider_override)


def _normalize_model_name(model_name: str) -> str:
    # Vercel gateway model IDs often include provider prefixes like "openai/".
    return model_name.split("/", 1)[1] if "/" in model_name else model_name


def _is_azure_apim_gateway(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    return "azure-api.net" in endpoint.lower()


def _is_azure_openai_v1_endpoint(endpoint: str | None) -> bool:
    if not endpoint:
        return False
    normalized = endpoint.lower().rstrip("/")
    return (
        "openai.azure.com" in normalized
        or "services.ai.azure.com" in normalized
        or normalized.endswith("/openai/v1")
        or "/openai/v1/" in normalized
    )


def _normalize_base_url(endpoint: str, suffix: str) -> str:
    return f"{endpoint.rstrip('/')}/{suffix.lstrip('/')}"


def _status_code_from_error(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code

    return None


def _retry_after_from_error(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None

    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is None:
        message = str(exc)
        match = re.search(r"retry after\s+(\d+(?:\.\d+)?)\s*seconds", message, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                return None
        return None

    try:
        return float(retry_after)
    except (TypeError, ValueError):
        return None


def _is_rate_limit_error(exc: Exception) -> bool:
    return _status_code_from_error(exc) == 429 or "rate_limit" in str(exc).lower()


def _log_rate_limit_wait(kind: str, attempt: int, max_retries: int, delay: float, batch_size: int | None = None) -> None:
    if os.getenv("LLM_RETRY_VERBOSE", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    suffix = f", batch_size={batch_size}" if batch_size is not None else ""
    print(
        f"[rate-limit] {kind} retry {attempt}/{max_retries}, waiting {delay:.1f}s{suffix}",
        file=sys.stderr,
        flush=True,
    )


def _get_azure_client(
    endpoint_override: str | None = None,
    api_key_override: str | None = None,
) -> AzureOpenAI:
    endpoint = endpoint_override or os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = api_key_override or os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    if not endpoint or not api_key:
        raise RuntimeError(
            "Azure AI is selected but AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY is missing."
        )

    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def _get_azure_chat_client() -> OpenAI | AzureOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_CHAT_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_CHAT_API_KEY")

    return _get_azure_client(endpoint, api_key)


def _get_azure_embedding_client() -> OpenAI | AzureOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT") 
    api_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY") 

    return _get_azure_client(endpoint, api_key)


def get_gateway_client(provider_override: str | None = None) -> OpenAI | AzureOpenAI:
    provider = _llm_provider(provider_override)
    if provider == "azure":
        return _get_azure_chat_client()

    api_key = os.getenv("AI_GATEWAY_API_KEY")
    if not api_key:
        raise RuntimeError("AI_GATEWAY_API_KEY is not configured.")
    return OpenAI(api_key=api_key, base_url="https://ai-gateway.vercel.sh/v1")


def create_chat_completion_stream(
    *,
    client: OpenAI | AzureOpenAI,
    model_name: str | None,
    provider_override: str | None = None,
    prompt: str,
    temperature: float = 1.0,
):
    provider = _llm_provider(provider_override)
    requested_model = (model_name or "").strip()

    if provider == "azure":
        resolved_model = requested_model or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT") or "gpt-4o-mini"
    elif provider == "vercel":
        fallback = _normalize_model_name(requested_model) if requested_model else "gpt-4o-mini"
        resolved_model = requested_model or os.getenv("VERCEL_CHAT_DEPLOYMENT") or fallback
    else:
        fallback = _normalize_model_name(requested_model) if requested_model else "gpt-4o-mini"
        resolved_model = requested_model or fallback
        
    max_retries = max(0, int(os.getenv("CHAT_MAX_RETRIES", "3")))
    base_delay = max(0.1, float(os.getenv("CHAT_RETRY_BASE_DELAY", "1.5")))
    max_delay = max(base_delay, float(os.getenv("CHAT_RETRY_MAX_DELAY", "20")))

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                stream=True,
            )
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc):
                raise

            if attempt >= max_retries:
                break

            retry_after = _retry_after_from_error(exc)
            delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2 ** attempt))
            _log_rate_limit_wait("chat", attempt + 1, max_retries, delay)
            time.sleep(delay)

    if last_error is not None:
        raise last_error

    raise RuntimeError("Failed to create chat completion stream.")


def create_chat_completion_text(
    *,
    client: OpenAI | AzureOpenAI,
    model_name: str | None,
    provider_override: str | None = None,
    prompt: str,
    temperature: float = 0.4,
) -> str:
    """Create a non-streaming chat completion and return plain text content."""
    provider = _llm_provider(provider_override)
    requested_model = (model_name or "").strip()

    if provider == "azure":
        resolved_model = requested_model or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT") or "gpt-4o-mini"
    elif provider == "vercel":
        fallback = _normalize_model_name(requested_model) if requested_model else "gpt-4o-mini"
        resolved_model = requested_model or os.getenv("VERCEL_CHAT_DEPLOYMENT") or fallback
    else:
        fallback = _normalize_model_name(requested_model) if requested_model else "gpt-4o-mini"
        resolved_model = requested_model or fallback

    max_retries = max(0, int(os.getenv("CHAT_MAX_RETRIES", "3")))
    base_delay = max(0.1, float(os.getenv("CHAT_RETRY_BASE_DELAY", "1.5")))
    max_delay = max(base_delay, float(os.getenv("CHAT_RETRY_MAX_DELAY", "20")))

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                stream=False,
            )
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise RuntimeError("Chat completion returned no choices.")
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if not content:
                raise RuntimeError("Chat completion returned empty content.")
            return str(content)
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc):
                raise

            if attempt >= max_retries:
                break

            retry_after = _retry_after_from_error(exc)
            delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2 ** attempt))
            _log_rate_limit_wait("chat", attempt + 1, max_retries, delay)
            time.sleep(delay)

    if last_error is not None:
        raise last_error

    raise RuntimeError("Failed to create chat completion.")


def create_embedding(
    *,
    input_text: str,
    model_name: str = "text-embedding-3-large",
    provider_override: str | None = None,
) -> list[float]:
    provider = _embedding_provider(provider_override)
    resolved_model = model_name
    embedding_client: OpenAI | AzureOpenAI

    if provider == "azure":
        embedding_client = _get_azure_embedding_client()
        resolved_model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or _normalize_model_name(model_name)
    else:
        api_key = os.getenv("AI_GATEWAY_API_KEY")
        if not api_key:
            raise RuntimeError("AI_GATEWAY_API_KEY is not configured.")
        embedding_client = OpenAI(api_key=api_key, base_url="https://ai-gateway.vercel.sh/v1")

    max_retries = max(0, int(os.getenv("EMBEDDING_MAX_RETRIES", "5")))
    base_delay = max(0.1, float(os.getenv("EMBEDDING_RETRY_BASE_DELAY", "2")))
    max_delay = max(base_delay, float(os.getenv("EMBEDDING_RETRY_MAX_DELAY", "90")))

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = embedding_client.embeddings.create(model=resolved_model, input=input_text)
            if not getattr(response, "data", None):
                raise RuntimeError("Embedding API returned no data.")
            return response.data[0].embedding
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc):
                raise
            if attempt >= max_retries:
                break
            retry_after = _retry_after_from_error(exc)
            delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2 ** attempt))
            _log_rate_limit_wait("embedding", attempt + 1, max_retries, delay)
            time.sleep(delay)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to create embedding.")


def create_embeddings(
    *,
    input_texts: list[str],
    model_name: str = "text-embedding-3-large",
    provider_override: str | None = None,
) -> list[list[float]]:
    if not input_texts:
        return []

    provider = _embedding_provider(provider_override)
    resolved_model = model_name
    embedding_client: OpenAI | AzureOpenAI

    if provider == "azure":
        embedding_client = _get_azure_embedding_client()
        resolved_model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or _normalize_model_name(model_name)
    else:
        api_key = os.getenv("AI_GATEWAY_API_KEY")
        if not api_key:
            raise RuntimeError("AI_GATEWAY_API_KEY is not configured.")
        embedding_client = OpenAI(api_key=api_key, base_url="https://ai-gateway.vercel.sh/v1")

    max_retries = max(0, int(os.getenv("EMBEDDING_MAX_RETRIES", "5")))
    base_delay = max(0.1, float(os.getenv("EMBEDDING_RETRY_BASE_DELAY", "2")))
    max_delay = max(base_delay, float(os.getenv("EMBEDDING_RETRY_MAX_DELAY", "90")))
    split_after = max(0, int(os.getenv("EMBEDDING_SPLIT_AFTER_RETRIES", "2")))

    def _request_batch(texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = embedding_client.embeddings.create(model=resolved_model, input=texts)
                if not getattr(response, "data", None):
                    raise RuntimeError("Embedding API returned no data.")
                return [item.embedding for item in response.data]
            except Exception as exc:
                last_error = exc
                if not _is_rate_limit_error(exc):
                    raise
                if attempt >= max_retries:
                    break
                if len(texts) > 1 and attempt + 1 >= split_after:
                    break
                retry_after = _retry_after_from_error(exc)
                delay = retry_after if retry_after is not None else min(max_delay, base_delay * (2 ** attempt))
                _log_rate_limit_wait("embeddings", attempt + 1, max_retries, delay, batch_size=len(texts))
                time.sleep(delay)

        if len(texts) > 1 and last_error is not None and _is_rate_limit_error(last_error):
            mid = len(texts) // 2
            left = _request_batch(texts[:mid])
            right = _request_batch(texts[mid:])
            return left + right

        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to create embeddings.")

    return _request_batch(input_texts)