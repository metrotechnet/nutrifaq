"""Model catalog loader for frontend-selectable chat models."""

from __future__ import annotations

import json
import os
from typing import Any
from api.services.blob_storage_service import get_container_client, has_blob_storage_config


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _catalog_blob_container_name() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_CONTAINER", "nutrifaq-config").strip()


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _catalog_blob_prefix() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_PREFIX", "").strip("/")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _catalog_blob_name() -> str:
    prefix = _catalog_blob_prefix()
    return f"{prefix}/accessible_models.json" if prefix else "accessible_models.json"


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _current_provider() -> str:
    return os.getenv("LLM_PROVIDER", "vercel").strip().lower()


# Purpose: Load configuration or persisted data and normalize the result for runtime use.
# Inputs/Outputs: See signature and return annotation for contract details.
def load_accessible_models() -> dict[str, Any]:
    if not has_blob_storage_config():
        return {
            "models": [],
            "default_model": None,
            "provider": _current_provider(),
            "message": "Azure Blob Storage is not configured.",
        }

    blob_name = _catalog_blob_name()
    blob_client = get_container_client(_catalog_blob_container_name()).get_blob_client(blob_name)

    try:
        raw_content = blob_client.download_blob().readall()
    except Exception as exc:
        return {
            "models": [],
            "default_model": None,
            "provider": _current_provider(),
            "message": f"Catalog blob not found or unreadable: {blob_name} ({exc})",
        }

    payload = json.loads(raw_content.decode("utf-8"))

    models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(models, list):
        models = []

    normalized: list[dict[str, str]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        normalized.append(
            {
                "id": model_id,
                "provider": str(item.get("provider") or "").strip().lower() or "unknown",
                "label": str(item.get("label") or model_id).strip(),
            }
        )

    provider = _current_provider()
    default_model = None
    for model in normalized:
        if model.get("provider") == provider:
            default_model = model.get("id")
            break

    if default_model is None and normalized:
        default_model = normalized[0].get("id")

    return {
        "models": normalized,
        "default_model": default_model,
        "provider": provider,
    }
