"""User management routes with Entra ID authentication and role-based access control."""

from __future__ import annotations

import base64
import os
import uuid
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.services.entra_auth_service import EntraUser, require_admin, require_collaborator
from api.services.user_management_service import (
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_COLLABORATOR,
    VALID_ROLES,
    list_assigned_roles,
    remove_assigned_role,
    set_assigned_role,
)

router = APIRouter()


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., description="Role to assign: admin, collaborator, or client")


class CreateUserRequest(BaseModel):
    email: str = Field(..., description="User principal name, e.g. user@contoso.com")
    display_name: str | None = Field(None, description="Display name for the user")
    password: str | None = Field(None, description="Initial password for the new Entra user")
    role: str = Field("client", description="Role to assign after creation: admin, collaborator, or client")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _get_graph_access_token() -> str:
    tenant_id = os.getenv("ENTRA_TENANT_ID", "").strip()
    client_id = os.getenv("ENTRA_CLIENT_ID", "").strip()
    client_secret = os.getenv("ENTRA_CLIENT_SECRET", "").strip()

    if not tenant_id or not client_id or not client_secret:
        raise RuntimeError("Missing ENTRA_TENANT_ID, ENTRA_CLIENT_ID or ENTRA_CLIENT_SECRET for Graph API creation.")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    response = requests.post(token_url, data=payload, timeout=30)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Graph access token response did not include access_token.")
    return token


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _get_verified_domains(token: str) -> tuple[list[str], str | None]:
    response = requests.get(
        "https://graph.microsoft.com/v1.0/domains?$select=id,isVerified,isDefault",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    domains: list[str] = []
    default_domain: str | None = None
    for item in payload.get("value", []):
        if not isinstance(item, dict):
            continue
        domain_id = str(item.get("id") or "").strip().lower()
        if not domain_id or not bool(item.get("isVerified")):
            continue
        domains.append(domain_id)
        if bool(item.get("isDefault")) and default_domain is None:
            default_domain = domain_id

    # Preserve insertion order while removing duplicates.
    deduped_domains = list(dict.fromkeys(domains))
    return deduped_domains, default_domain


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _create_entra_user_via_graph(email: str, display_name: str | None, password: str | None) -> dict[str, Any]:
    token = _get_graph_access_token()

    local_part, input_domain = email.split("@", 1)
    user_name = (display_name or local_part).strip()
    mail_nickname = local_part.strip()
    password_value = password or "P@ssw0rd!2026"
    requested_domain = input_domain.strip().lower()

    verified_domains: list[str] = []
    default_verified_domain: str | None = None
    try:
        verified_domains, default_verified_domain = _get_verified_domains(token)
    except Exception:
        # If domain lookup fails, keep the original requested UPN and let Graph validate.
        verified_domains = []
        default_verified_domain = None

    upn_email = email
    if verified_domains and requested_domain not in verified_domains:
        selected_domain = default_verified_domain or verified_domains[0]
        upn_email = f"{mail_nickname}@{selected_domain}"

    payload = {
        "accountEnabled": True,
        "displayName": user_name,
        "mailNickname": mail_nickname,
        "userPrincipalName": upn_email,
        "passwordProfile": {
            "password": password_value,
            "forceChangePasswordNextSignIn": False,
        },
    }
    if upn_email.lower() != email.lower():
        payload["otherMails"] = [email]

    # Purpose: Internal helper used to keep the main workflow readable and maintainable.
    # Inputs/Outputs: See signature and return annotation for contract details.
    def _post_user(candidate_payload: dict[str, Any]) -> requests.Response:
        return requests.post(
            "https://graph.microsoft.com/v1.0/users",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=candidate_payload,
            timeout=30,
        )

    # Purpose: Internal helper used to keep the main workflow readable and maintainable.
    # Inputs/Outputs: See signature and return annotation for contract details.
    def _error_message(candidate_response: requests.Response) -> str:
        try:
            payload = candidate_response.json()
            return str(payload.get("error", {}).get("message", ""))
        except Exception:
            return ""

    response = _post_user(payload)

    if response.status_code == 400:
        message = _error_message(response)
        if "SourceAnchor is a required property for creation of a federated user" in message:
            source_anchor = base64.b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")
            retry_payload = dict(payload)
            retry_payload["onPremisesImmutableId"] = source_anchor
            response = _post_user(retry_payload)

    if response.status_code == 400:
        message = _error_message(response)
        invalid_domain_msg = "The domain portion of the userPrincipalName property is invalid"
        fallback_upn_domain = os.getenv("ENTRA_UPN_DOMAIN", "").strip().lower()
        if invalid_domain_msg in message and fallback_upn_domain:
            retry_payload = dict(payload)
            retry_payload["userPrincipalName"] = f"{mail_nickname}@{fallback_upn_domain}"
            retry_payload["otherMails"] = [email]
            response = _post_user(retry_payload)

            if response.status_code == 400:
                second_message = _error_message(response)
                if "SourceAnchor is a required property for creation of a federated user" in second_message:
                    retry_payload["onPremisesImmutableId"] = base64.b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")
                    response = _post_user(retry_payload)

    if response.status_code in {400, 401, 403, 409}:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise HTTPException(status_code=400, detail=f"Graph user creation failed: {detail}")
    response.raise_for_status()
    user = response.json()
    return user


@router.get("/api/users/me")
async def get_current_user_profile(user: EntraUser = Depends(require_collaborator)):
    """Return identity and effective role for the authenticated Entra user."""
    return {
        "object_id": user.object_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "token_roles": user.token_roles,
    }


@router.post("/api/users")
async def create_user(
    body: CreateUserRequest,
    current_user: EntraUser = Depends(require_admin),
):
    """Create an Entra user via Graph and assign a local app role."""
    normalized_email = body.email.strip()
    if "@" not in normalized_email:
        raise HTTPException(status_code=400, detail="email must be a valid UPN like user@domain.com")

    normalized_role = body.role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {sorted(VALID_ROLES)}")

    try:
        graph_user = _create_entra_user_via_graph(normalized_email, body.display_name, body.password)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    object_id = str(graph_user.get("id") or graph_user.get("objectId") or "").strip()
    if not object_id:
        raise HTTPException(status_code=500, detail="Graph user creation succeeded but no object id was returned.")

    assignment = set_assigned_role(object_id, normalized_role, assigned_by=current_user.object_id)
    return {
        "user": {
            "object_id": object_id,
            "email": normalized_email,
            "display_name": body.display_name or normalized_email.split("@")[0],
            "user_principal_name": graph_user.get("userPrincipalName", normalized_email),
        },
        "role": assignment,
    }


@router.get("/api/users")
async def list_users(_: EntraUser = Depends(require_admin)):
    """List explicit role assignments stored by the API."""
    return {
        "roles": list_assigned_roles(),
        "available_roles": [ROLE_ADMIN, ROLE_COLLABORATOR, ROLE_CLIENT],
    }


@router.put("/api/users/{user_object_id}/role")
async def update_user_role(
    user_object_id: str,
    body: UpdateUserRoleRequest,
    current_user: EntraUser = Depends(require_admin),
):
    """Set role assignment for a user object ID."""
    normalized_role = body.role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {sorted(VALID_ROLES)}")

    result = set_assigned_role(user_object_id, normalized_role, assigned_by=current_user.object_id)
    return {
        "object_id": user_object_id,
        "assignment": result,
    }


@router.delete("/api/users/{user_object_id}/role")
async def delete_user_role(
    user_object_id: str,
    _: EntraUser = Depends(require_admin),
):
    """Remove role assignment for a user object ID."""
    deleted = remove_assigned_role(user_object_id)
    return {
        "object_id": user_object_id,
        "deleted": deleted,
    }
