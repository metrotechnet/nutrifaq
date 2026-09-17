"""Local role assignment store for Entra-authenticated users."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_ADMIN = "admin"
ROLE_COLLABORATOR = "collaborator"
VALID_ROLES = {ROLE_ADMIN, ROLE_COLLABORATOR}

_API_ROOT = Path(__file__).resolve().parents[1]
_ROLE_ASSIGNMENTS_FILE = _API_ROOT / "config" / "user_roles.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_payload() -> dict[str, Any]:
    return {"users": {}}


def _load_payload() -> dict[str, Any]:
    if not _ROLE_ASSIGNMENTS_FILE.exists():
        return _default_payload()

    try:
        with _ROLE_ASSIGNMENTS_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return _default_payload()

    if not isinstance(payload, dict):
        return _default_payload()

    users = payload.get("users")
    if not isinstance(users, dict):
        payload["users"] = {}
    return payload


def _save_payload(payload: dict[str, Any]) -> None:
    _ROLE_ASSIGNMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _ROLE_ASSIGNMENTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


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
