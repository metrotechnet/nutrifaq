"""User management routes with Entra ID authentication and role-based access control."""

from __future__ import annotations

from typing import Any

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
