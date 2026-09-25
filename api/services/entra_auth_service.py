"""Microsoft Entra ID authentication and role-based authorization helpers."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
import requests
from fastapi import Depends, HTTPException, Request, status
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


@dataclass
class EntraUser:
    object_id: str
    username: str
    display_name: str
    role: str
    token_roles: list[str]
    claims: dict[str, Any]


@lru_cache(maxsize=1)
# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
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
# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _jwks_client() -> jwt.PyJWKClient:
    openid_cfg = _openid_configuration()
    jwks_uri = str(openid_cfg.get("jwks_uri", "")).strip()
    if not jwks_uri:
        raise RuntimeError("jwks_uri not found in Entra OpenID configuration.")
    return jwt.PyJWKClient(jwks_uri)


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
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


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _token_roles(claims: dict[str, Any]) -> list[str]:
    raw_roles = claims.get("roles")
    if isinstance(raw_roles, list):
        values = raw_roles
    elif isinstance(raw_roles, str):
        values = [raw_roles]
    else:
        values = []

    return [str(role).strip().lower() for role in values if str(role).strip()]


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _effective_role(object_id: str, claim_roles: list[str]) -> str:
    _ = claim_roles  # Role authorization intentionally ignores token roles.

    assigned = get_assigned_role(object_id)
    if assigned:
        return assigned

    # Default every authenticated Entra user to admin unless explicitly overridden.
    return ROLE_ADMIN


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _decode_access_token(token: str) -> dict[str, Any]:
    openid_cfg = _openid_configuration()
    issuer = str(openid_cfg.get("issuer", "")).strip()
    if not issuer:
        raise RuntimeError("issuer not found in Entra OpenID configuration.")

    tenant_id = os.getenv("ENTRA_TENANT_ID", "").strip()
    if not tenant_id:
        raise RuntimeError("ENTRA_TENANT_ID is required for issuer validation.")

    audience = _expected_audience()
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        options={"require": ["exp", "iat", "iss", "aud"], "verify_iss": False},
    )
    if not isinstance(claims, dict):
        raise RuntimeError("Invalid token claims payload.")

    # Accept equivalent Entra issuer variants for the configured tenant (v1/v2 forms).
    token_issuer = str(claims.get("iss", "")).strip()
    normalized_issuer = token_issuer.rstrip("/").lower()
    allowed_issuers = {
        issuer.rstrip("/").lower(),
        f"https://login.microsoftonline.com/{tenant_id}/v2.0".rstrip("/").lower(),
        f"https://sts.windows.net/{tenant_id}".rstrip("/").lower(),
    }
    if normalized_issuer not in allowed_issuers:
        raise RuntimeError(f"Invalid issuer '{token_issuer}' for tenant '{tenant_id}'.")

    token_tid = str(claims.get("tid", "")).strip()
    if token_tid and token_tid.lower() != tenant_id.lower():
        raise RuntimeError(f"Invalid tenant '{token_tid}'. Expected '{tenant_id}'.")

    return claims


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
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


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> EntraUser:
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


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _require_min_role(min_role: str):
    if min_role not in _ROLE_ORDER:
        raise ValueError(f"Unsupported role guard: {min_role}")

    # Purpose: Internal helper used to keep the main workflow readable and maintainable.
    # Inputs/Outputs: See signature and return annotation for contract details.
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


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
async def require_client_or_query_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> EntraUser:
    request_path = (request.url.path or "").rstrip("/") or "/"
    is_query_endpoint = request_path == "/query"

    expected_key = os.getenv("QUERY_ACCESS_KEY", "").strip()
    provided_key = request.headers.get("X-Client-Key", "").strip()

    if is_query_endpoint and expected_key and provided_key and hmac.compare_digest(provided_key, expected_key):
        return EntraUser(
            object_id="query-key-user",
            username="query-key@local",
            display_name="Query Key User",
            role=ROLE_CLIENT,
            token_roles=[ROLE_CLIENT],
            claims={"mode": "query_key"},
        )

    user = await get_current_user(credentials)
    if _ROLE_ORDER.get(user.role, 0) < _ROLE_ORDER[ROLE_CLIENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {ROLE_CLIENT}.",
        )
    return user
