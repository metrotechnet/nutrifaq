"""Local role assignment store for Entra-authenticated users."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from api.services.blob_storage_service import get_container_client, has_blob_storage_config

ROLE_ADMIN = "admin"
ROLE_COLLABORATOR = "collaborator"
ROLE_CLIENT = "client"
VALID_ROLES = {ROLE_ADMIN, ROLE_COLLABORATOR, ROLE_CLIENT}

def _roles_blob_container_name() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_CONTAINER", "nutrifaq-config").strip()


def _roles_blob_prefix() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_PREFIX", "").strip("/")


def _roles_blob_name() -> str:
    prefix = _roles_blob_prefix()
    return f"{prefix}/user_roles.json" if prefix else "user_roles.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_payload() -> dict[str, Any]:
    return {"users": {}}


def _load_payload() -> dict[str, Any]:
    if not has_blob_storage_config():
        return _default_payload()

    try:
        blob_name = _roles_blob_name()
        blob_client = get_container_client(_roles_blob_container_name()).get_blob_client(blob_name)
        raw_content = blob_client.download_blob().readall()
        payload = json.loads(raw_content.decode("utf-8"))
    except Exception:
        return _default_payload()

    if not isinstance(payload, dict):
        return _default_payload()

    users = payload.get("users")
    if not isinstance(users, dict):
        payload["users"] = {}
    return payload


def _save_payload(payload: dict[str, Any]) -> None:
    if not has_blob_storage_config():
        raise RuntimeError("Azure Blob Storage is required to save role assignments.")

    blob_name = _roles_blob_name()
    encoded_payload = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    blob_client = get_container_client(_roles_blob_container_name()).get_blob_client(blob_name)
    blob_client.upload_blob(encoded_payload, overwrite=True)


def get_assigned_role(user_object_id: str) -> str | None:
    payload = _load_payload()
    users = payload.get("users", {})
    entry = users.get(user_object_id)
    if not isinstance(entry, dict):
        return None

    role = str(entry.get("role", "")).strip().lower()
    if role in VALID_ROLES:
        return role
    return None


def set_assigned_role(user_object_id: str, role: str, assigned_by: str) -> dict[str, Any]:
    role = role.strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported role '{role}'. Expected one of: {sorted(VALID_ROLES)}")

    payload = _load_payload()
    users = payload.setdefault("users", {})
    users[user_object_id] = {
        "role": role,
        "updated_at": _utc_now_iso(),
        "updated_by": assigned_by,
    }
    _save_payload(payload)
    return users[user_object_id]


def remove_assigned_role(user_object_id: str) -> bool:
    payload = _load_payload()
    users = payload.get("users", {})
    if user_object_id not in users:
        return False

    del users[user_object_id]
    _save_payload(payload)
    return True


def list_assigned_roles() -> dict[str, dict[str, Any]]:
    payload = _load_payload()
    users = payload.get("users", {})
    return users if isinstance(users, dict) else {}
