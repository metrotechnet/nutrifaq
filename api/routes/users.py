"""Local user management routes with role-based access control."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException, UserAlreadyExists
from fastapi_users.password import PasswordHelper
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from api.services.entra_auth_service import (
    EntraUser,
    User,
    UserCreate,
    UserManager,
    async_session_maker,
    require_admin,
    require_collaborator,
)
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
password_helper = PasswordHelper()


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(..., description="Role to assign: admin, collaborator, or client")


class UpdateUserPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, description="New password")


class CreateUserRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address used to sign in")
    display_name: str | None = Field(None, description="Optional display name")
    password: str = Field(..., min_length=8, description="Initial password")
    role: str = Field("client", description="Role to assign after creation: admin, collaborator, or client")


def _normalize_role(value: str) -> str:
    role = value.strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {sorted(VALID_ROLES)}")
    return role


def _serialize_user(user: User, assigned_roles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    user_id = str(user.id)
    assignment = assigned_roles.get(user_id, {}) if isinstance(assigned_roles, dict) else {}
    assigned_role = str(assignment.get("role", "")).strip().lower() or None
    effective_role = assigned_role or (ROLE_ADMIN if bool(user.is_superuser) else ROLE_CLIENT)
    email = str(user.email or "").strip()

    return {
        "object_id": user_id,
        "email": email,
        "display_name": email.split("@")[0] if "@" in email else email,
        "role": effective_role,
        "assigned_role": assigned_role,
        "is_active": bool(user.is_active),
        "is_superuser": bool(user.is_superuser),
        "is_verified": bool(user.is_verified),
    }


async def _get_user_by_id_or_404(user_object_id: str) -> User:
    try:
        user_uuid = UUID(user_object_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user_object_id (expected UUID).") from exc

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_uuid))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return user


@router.get("/api/users/me")
async def get_current_user_profile(user: EntraUser = Depends(require_collaborator)):
    """Return identity and effective role for the authenticated local user."""
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
    """Create a local user and assign an application role."""
    normalized_role = _normalize_role(body.role)

    user_create = UserCreate(
        email=str(body.email).strip().lower(),
        password=body.password,
        is_active=True,
        is_superuser=normalized_role == ROLE_ADMIN,
        is_verified=True,
    )

    try:
        async with async_session_maker() as session:
            user_db = SQLAlchemyUserDatabase(session, User)
            manager = UserManager(user_db)
            created = await manager.create(user_create, safe=False)
    except UserAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="A user with this email already exists.") from exc
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=f"Invalid password: {exc.reason}") from exc

    assignment: dict[str, Any] | None = None
    try:
        assignment = set_assigned_role(str(created.id), normalized_role, assigned_by=current_user.object_id)
    except RuntimeError as exc:
        if normalized_role != ROLE_ADMIN:
            async with async_session_maker() as cleanup_session:
                result = await cleanup_session.execute(select(User).where(User.id == created.id))
                user_to_delete = result.scalar_one_or_none()
                if user_to_delete is not None:
                    await cleanup_session.delete(user_to_delete)
                    await cleanup_session.commit()
            raise HTTPException(
                status_code=500,
                detail="Unable to persist role assignment. User creation has been rolled back.",
            ) from exc

    return {
        "user": {
            "object_id": str(created.id),
            "email": str(created.email),
            "display_name": body.display_name or str(created.email).split("@")[0],
        },
        "role": assignment or {"role": normalized_role},
    }


@router.get("/api/users")
async def list_users(_: EntraUser = Depends(require_admin)):
    """List local users and role assignments."""
    async with async_session_maker() as session:
        result = await session.execute(select(User).order_by(User.email.asc()))
        users = list(result.scalars().all())

    assigned_roles = list_assigned_roles()
    known_user_ids = {str(user.id) for user in users}
    orphan_roles = {
        user_id: assignment
        for user_id, assignment in assigned_roles.items()
        if user_id not in known_user_ids
    }

    return {
        "users": [_serialize_user(user, assigned_roles) for user in users],
        "roles": assigned_roles,
        "orphan_roles": orphan_roles,
        "available_roles": [ROLE_ADMIN, ROLE_COLLABORATOR, ROLE_CLIENT],
    }


@router.put("/api/users/{user_object_id}/role")
async def update_user_role(
    user_object_id: str,
    body: UpdateUserRoleRequest,
    current_user: EntraUser = Depends(require_admin),
):
    """Set role assignment for a local user."""
    normalized_role = _normalize_role(body.role)
    user = await _get_user_by_id_or_404(user_object_id)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        persisted_user = result.scalar_one_or_none()
        if persisted_user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        persisted_user.is_superuser = normalized_role == ROLE_ADMIN
        session.add(persisted_user)
        await session.commit()

    try:
        result = set_assigned_role(str(user.id), normalized_role, assigned_by=current_user.object_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to persist role assignment: {exc}") from exc

    return {
        "object_id": str(user.id),
        "assignment": result,
    }


@router.put("/api/users/{user_object_id}/password")
async def update_user_password(
    user_object_id: str,
    body: UpdateUserPasswordRequest,
    _: EntraUser = Depends(require_admin),
):
    """Set a new password for a local user."""
    user = await _get_user_by_id_or_404(user_object_id)

    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        try:
            await manager.validate_password(body.password, user)
        except InvalidPasswordException as exc:
            raise HTTPException(status_code=400, detail=f"Invalid password: {exc.reason}") from exc

        result = await session.execute(select(User).where(User.id == user.id))
        persisted_user = result.scalar_one_or_none()
        if persisted_user is None:
            raise HTTPException(status_code=404, detail="User not found.")

        persisted_user.hashed_password = password_helper.hash(body.password)
        session.add(persisted_user)
        await session.commit()

    return {"object_id": str(user.id), "password_updated": True}


@router.delete("/api/users/{user_object_id}")
async def delete_user(
    user_object_id: str,
    current_user: EntraUser = Depends(require_admin),
):
    """Delete a local user account and associated app role assignment."""
    if user_object_id == current_user.object_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    user = await _get_user_by_id_or_404(user_object_id)
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        persisted_user = result.scalar_one_or_none()
        if persisted_user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        await session.delete(persisted_user)
        await session.commit()

    role_deleted = remove_assigned_role(str(user.id))
    return {
        "object_id": str(user.id),
        "deleted": True,
        "role_deleted": role_deleted,
    }


@router.delete("/api/users/{user_object_id}/role")
async def delete_user_role(
    user_object_id: str,
    _: EntraUser = Depends(require_admin),
):
    """Remove role assignment for a local user object ID."""
    _ = await _get_user_by_id_or_404(user_object_id)
    deleted = remove_assigned_role(user_object_id)
    return {
        "object_id": user_object_id,
        "deleted": deleted,
    }
