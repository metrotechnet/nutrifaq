"""Model catalog loader for frontend-selectable chat models."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
MODEL_CATALOG_PATH = API_ROOT / "config" / "accessible_models.json"


def _current_provider() -> str:
    return os.getenv("LLM_PROVIDER", "vercel").strip().lower()


def load_accessible_models() -> dict[str, Any]:
    if not MODEL_CATALOG_PATH.exists():
        return {
            "models": [],
            "default_model": None,
            "provider": _current_provider(),
            "message": f"Catalog file not found: {MODEL_CATALOG_PATH}",
        }

    with MODEL_CATALOG_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

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
