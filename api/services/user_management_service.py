"""Local role assignment and user auth metadata store in auth SQLite DB."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

ROLE_ADMIN = "admin"
ROLE_COLLABORATOR = "collaborator"
ROLE_CLIENT = "client"
VALID_ROLES = {ROLE_ADMIN, ROLE_COLLABORATOR}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_AUTH_SQLITE_URL = "sqlite+aiosqlite:///./nutrifaq_auth.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_auth_database_url() -> str:
    explicit = os.getenv("AUTH_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    return _DEFAULT_AUTH_SQLITE_URL


def _auth_sqlite_db_path() -> Path:
    raw_url = _resolve_auth_database_url()
    if not raw_url.startswith("sqlite"):
        raise RuntimeError("Role metadata requires a SQLite auth database.")

    parsed = make_url(raw_url)
    database = (parsed.database or "").strip()
    if not database or database == ":memory:" or database.startswith("file:"):
        raise RuntimeError("Role metadata requires a file-based SQLite auth database.")

    db_path = Path(database).expanduser()
    if not db_path.is_absolute():
        db_path = (_PROJECT_ROOT / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_auth_sqlite_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user_metadata (
            user_object_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL
        )
        """
    )
    return conn


def get_assigned_role(user_object_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT role FROM auth_user_metadata WHERE user_object_id = ?",
            (user_object_id,),
        ).fetchone()

    if row is None:
        return None
    role = str(row["role"] or "").strip().lower()
    if role == ROLE_CLIENT:
        return ROLE_COLLABORATOR
    if role in VALID_ROLES:
        return role
    return None


def set_assigned_role(user_object_id: str, role: str, assigned_by: str) -> dict[str, Any]:
    role = role.strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported role '{role}'. Expected one of: {sorted(VALID_ROLES)}")

    with _connect() as conn:
        row = conn.execute(
            "SELECT must_change_password FROM auth_user_metadata WHERE user_object_id = ?",
            (user_object_id,),
        ).fetchone()
        must_change_password = 1 if row and int(row["must_change_password"] or 0) else 0
        updated_at = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO auth_user_metadata (user_object_id, role, must_change_password, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_object_id) DO UPDATE SET
                role = excluded.role,
                must_change_password = excluded.must_change_password,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (user_object_id, role, must_change_password, updated_at, assigned_by),
        )
        conn.commit()

    return {
        "role": role,
        "must_change_password": bool(must_change_password),
        "updated_at": updated_at,
        "updated_by": assigned_by,
    }


def is_password_change_required(user_object_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT must_change_password FROM auth_user_metadata WHERE user_object_id = ?",
            (user_object_id,),
        ).fetchone()
    return bool(int(row["must_change_password"])) if row is not None else False


def set_password_change_required(user_object_id: str, required: bool, updated_by: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT role FROM auth_user_metadata WHERE user_object_id = ?",
            (user_object_id,),
        ).fetchone()
        role = str(row["role"] if row else "").strip().lower()
        normalized_role = role if role in VALID_ROLES else ROLE_COLLABORATOR
        must_change_password = 1 if required else 0
        updated_at = _utc_now_iso()
        conn.execute(
            """
            INSERT INTO auth_user_metadata (user_object_id, role, must_change_password, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_object_id) DO UPDATE SET
                role = excluded.role,
                must_change_password = excluded.must_change_password,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (user_object_id, normalized_role, must_change_password, updated_at, updated_by),
        )
        conn.commit()

    return {
        "role": normalized_role,
        "must_change_password": bool(must_change_password),
        "updated_at": updated_at,
        "updated_by": updated_by,
    }


def remove_assigned_role(user_object_id: str) -> bool:
    with _connect() as conn:
        result = conn.execute(
            "DELETE FROM auth_user_metadata WHERE user_object_id = ?",
            (user_object_id,),
        )
        conn.commit()
    return result.rowcount > 0


def list_assigned_roles() -> dict[str, dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT user_object_id, role, must_change_password, updated_at, updated_by FROM auth_user_metadata"
        ).fetchall()

    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        role = str(row["role"] or "").strip().lower()
        if role == ROLE_CLIENT:
            role = ROLE_COLLABORATOR
        if role not in VALID_ROLES:
            role = ROLE_COLLABORATOR
        payload[str(row["user_object_id"])] = {
            "role": role,
            "must_change_password": bool(int(row["must_change_password"] or 0)),
            "updated_at": str(row["updated_at"] or ""),
            "updated_by": str(row["updated_by"] or ""),
        }
    return payload
