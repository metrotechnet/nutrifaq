"""Microsoft Entra ID authentication and role-based authorization helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.services.user_management_service import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_COLLABORATOR,
    get_assigned_role,
)

_security = HTTPBearer(auto_error=False)
_ROLE_ORDER = {
    ROLE_CLIENT: 1,
    ROLE_COLLABORATOR: 2,
    ROLE_ADMIN: 3,
}


def _is_demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EntraUser:
    object_id: str
    username: str
    display_name: str
    role: str
    token_roles: list[str]
    claims: dict[str, Any]


@lru_cache(maxsize=1)
def _openid_configuration() -> dict[str, Any]:
    tenant_id = os.getenv("ENTRA_TENANT_ID", "").strip()
    if not tenant_id:
        raise RuntimeError("ENTRA_TENANT_ID is required for Entra ID authentication.")

    config_url = os.getenv(
        "ENTRA_OPENID_CONFIG_URL",
        f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration",
    ).strip()

    response = requests.get(config_url, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Invalid OpenID configuration payload from Entra ID.")
    return payload


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    openid_cfg = _openid_configuration()
    jwks_uri = str(openid_cfg.get("jwks_uri", "")).strip()
    if not jwks_uri:
        raise RuntimeError("jwks_uri not found in Entra OpenID configuration.")
    return jwt.PyJWKClient(jwks_uri)


def _expected_audience() -> str | list[str]:
    raw = os.getenv("ENTRA_AUDIENCE", "").strip()
    if raw:
        values = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        client_id = os.getenv("ENTRA_CLIENT_ID", "").strip()
        values = [client_id] if client_id else []

    if not values:
        raise RuntimeError("Set ENTRA_AUDIENCE or ENTRA_CLIENT_ID for token audience validation.")
    return values[0] if len(values) == 1 else values


def _token_roles(claims: dict[str, Any]) -> list[str]:
    raw_roles = claims.get("roles")
    if isinstance(raw_roles, list):
        values = raw_roles
    elif isinstance(raw_roles, str):
        values = [raw_roles]
    else:
        values = []

    return [str(role).strip().lower() for role in values if str(role).strip()]


def _effective_role(object_id: str, claim_roles: list[str]) -> str:
    _ = claim_roles  # Role authorization intentionally ignores token roles.

    assigned = get_assigned_role(object_id)
    if assigned:
        return assigned

    return ROLE_COLLABORATOR


def _decode_access_token(token: str) -> dict[str, Any]:
    openid_cfg = _openid_configuration()
    issuer = str(openid_cfg.get("issuer", "")).strip()
    if not issuer:
        raise RuntimeError("issuer not found in Entra OpenID configuration.")

    audience = _expected_audience()
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )
    if not isinstance(claims, dict):
        raise RuntimeError("Invalid token claims payload.")
    return claims


def _build_user(claims: dict[str, Any]) -> EntraUser:
    object_id = str(claims.get("oid") or claims.get("sub") or "").strip()
    if not object_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing oid/sub claim.")

    username = str(
        claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("email")
        or object_id
    ).strip()
    display_name = str(claims.get("name") or username).strip()
    token_roles = _token_roles(claims)
    role = _effective_role(object_id, token_roles)

    return EntraUser(
        object_id=object_id,
        username=username,
        display_name=display_name,
        role=role,
        token_roles=token_roles,
        claims=claims,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> EntraUser:
    if _is_demo_mode_enabled():
        return EntraUser(
            object_id="demo-user",
            username="demo@local",
            display_name="Demo User",
            role=ROLE_ADMIN,
            token_roles=[ROLE_ADMIN],
            claims={"mode": "demo"},
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = credentials.credentials
    try:
        claims = _decode_access_token(token)
        return _build_user(claims)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc


def _require_min_role(min_role: str):
    if min_role not in _ROLE_ORDER:
        raise ValueError(f"Unsupported role guard: {min_role}")

    async def _guard(user: EntraUser = Depends(get_current_user)) -> EntraUser:
        if _ROLE_ORDER.get(user.role, 0) < _ROLE_ORDER[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {min_role}.",
            )
        return user

    return _guard


require_collaborator = _require_min_role(ROLE_COLLABORATOR)
require_admin = _require_min_role(ROLE_ADMIN)
require_client = _require_min_role(ROLE_CLIENT)
