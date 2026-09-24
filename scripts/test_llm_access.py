"""Azure-only runtime checks for chat, embeddings, and Chroma compatibility.

Usage:
  python scripts/test_llm_access.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.services.query_chromadb import query_chromadb
from api.services.llm_service import create_chat_completion_stream, create_embedding, get_gateway_client


def _print_env() -> None:
    keys = [
        "LLM_PROVIDER",
        "CHAT_MAX_RETRIES",
        "CHAT_RETRY_BASE_DELAY",
        "CHAT_RETRY_MAX_DELAY",
        "EMBEDDING_PROVIDER",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    ]
    print("=== Effective env ===")
    for k in keys:
        v = os.getenv(k, "")
        print(f"{k}={v}")
    print()


def _test_embedding_access() -> tuple[bool, list[float] | None]:
    print("=== Test 1: Azure embedding access ===")
    try:
        vec = create_embedding(input_text="dimension check", model_name="text-embedding-3-large")
        print(f"embedding length: {len(vec)}")
        print("PASS")
        print()
        return True, vec
    except Exception as exc:
        print(f"FAIL: {exc}")
        print()
        return False, None


def _extract_first_text(stream) -> str:
    text = ""
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if content:
            text += content
            if text.strip():
                break
    return text.strip()


def _test_chat_access() -> bool:
    print("=== Test 2: Azure chat access ===")
    try:
        client = get_gateway_client()
        stream = create_chat_completion_stream(
            client=client,
            model_name="openai/gpt-4.1-mini",
            prompt="Reply with exactly: OK",
            temperature=0,
        )
        text = _extract_first_text(stream)
        ok = text.upper() == "OK"
        print(f"response: {text}")
        print("PASS" if ok else "FAIL (expected exact OK)")
        print()
        return ok
    except Exception as exc:
        print(f"FAIL: {exc}")
        print()
        return False


def _test_chroma_compatibility(vec: list[float] | None) -> bool:
    print("=== Test 3: Chroma query compatibility ===")
    if vec is None:
        print("SKIP (no embedding vector available)")
        print()
        return False

    try:
        result = query_chromadb(
            project_name="nutrifaq",
            collection_name="nutrifaq-collection",
            data={
                "query_embedding": vec,
                "n_results": 1,
                "include": ["documents"],
            },
        )

        if isinstance(result, dict) and result.get("error"):
            details = result.get("details", "")
            print(f"FAIL: {details or result['error']}")
            print()
            return False

        print("PASS")
        print()
        return True
    except Exception as exc:
        print(f"FAIL: {exc}")
        print()
        return False

