"""Local authentication and role-based authorization powered by fastapi-users."""

from __future__ import annotations

import hmac
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import quote_plus

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

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
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "auth_users"


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


@dataclass
class EntraUser:
    object_id: str
    username: str
    display_name: str
    role: str
    token_roles: list[str]
    claims: dict[str, Any]


def _build_azure_sql_database_url() -> str:
    user = os.getenv("AUTH_SQL_USER", "").strip()
    password = os.getenv("AUTH_SQL_PASSWORD", "").strip()
    server = os.getenv("AUTH_SQL_SERVER", "").strip()
    database = os.getenv("AUTH_SQL_DATABASE", "").strip()
    port = os.getenv("AUTH_SQL_PORT", "1433").strip() or "1433"
    driver = os.getenv("AUTH_SQL_DRIVER", "ODBC Driver 18 for SQL Server").strip() or "ODBC Driver 18 for SQL Server"

    missing = [
        name for name, value in (
            ("AUTH_SQL_USER", user),
            ("AUTH_SQL_PASSWORD", password),
            ("AUTH_SQL_SERVER", server),
            ("AUTH_SQL_DATABASE", database),
        ) if not value
    ]
    if missing:
        missing_values = ", ".join(missing)
        raise RuntimeError(f"Missing Azure SQL settings for auth DB: {missing_values}")

    encoded_user = quote_plus(user)
    encoded_password = quote_plus(password)
    encoded_driver = quote_plus(driver)
    return (
        f"mssql+aioodbc://{encoded_user}:{encoded_password}@{server}:{port}/{database}"
        f"?driver={encoded_driver}&Encrypt=yes&TrustServerCertificate=no"
    )


def _resolve_auth_database_url() -> str:
    explicit = os.getenv("AUTH_DATABASE_URL", "").strip()
    if explicit:
        return _prepare_sqlite_database_url(explicit)

    backend = os.getenv("AUTH_DB_BACKEND", "sqlite").strip().lower()
    if backend == "azure_sql":
        return _build_azure_sql_database_url()

    return _prepare_sqlite_database_url("sqlite+aiosqlite:///./nutrifaq_auth.db")


def _prepare_sqlite_database_url(raw_url: str) -> str:
    if not raw_url.startswith("sqlite"):
        return raw_url

    parsed = make_url(raw_url)
    database = (parsed.database or "").strip()
    if not database or database == ":memory:" or database.startswith("file:"):
        return raw_url

    db_path = Path(database).expanduser()
    if not db_path.is_absolute():
        db_path = (_PROJECT_ROOT / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(parsed.set(database=db_path.as_posix()))


DATABASE_URL = _resolve_auth_database_url()
AUTH_SECRET = os.getenv("AUTH_SECRET", os.getenv("JWT_SECRET", "change-me-in-production")).strip()
AUTH_CREATE_DEFAULT_ADMIN = os.getenv("AUTH_CREATE_DEFAULT_ADMIN", "1").strip().lower() in {"1", "true", "yes", "on"}
AUTH_DEFAULT_ADMIN_EMAIL = os.getenv("AUTH_DEFAULT_ADMIN_EMAIL", "admin@example.com").strip()
AUTH_DEFAULT_ADMIN_PASSWORD = os.getenv("AUTH_DEFAULT_ADMIN_PASSWORD", "ChangeMe!123").strip()

engine = create_async_engine(DATABASE_URL, future=True, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = AUTH_SECRET
    verification_token_secret = AUTH_SECRET


async def get_user_manager(user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db)) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=AUTH_SECRET, lifetime_seconds=60 * 60 * 12)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
_current_active_user = fastapi_users.current_user(active=True)


def _effective_role(user: User) -> str:
    assigned = get_assigned_role(str(user.id))
    if assigned:
        return assigned
    if bool(user.is_superuser):
        return ROLE_ADMIN
    return ROLE_CLIENT


def _build_user(user: User) -> EntraUser:
    username = str(user.email or user.id).strip()
    return EntraUser(
        object_id=str(user.id),
        username=username,
        display_name=username,
        role=_effective_role(user),
        token_roles=[],
        claims={"auth": "local_jwt"},
    )


async def get_current_user(user: User = Depends(_current_active_user)) -> EntraUser:
    return _build_user(user)


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

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = credentials.credentials
    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        user = await get_jwt_strategy().read_token(token, manager)

    if user is None or not bool(user.is_active):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")

    mapped = _build_user(user)
    if _ROLE_ORDER.get(mapped.role, 0) < _ROLE_ORDER[ROLE_CLIENT]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: {ROLE_CLIENT}.",
        )
    return mapped


async def initialize_auth() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    if not AUTH_CREATE_DEFAULT_ADMIN or not AUTH_DEFAULT_ADMIN_EMAIL or not AUTH_DEFAULT_ADMIN_PASSWORD:
        return

    async with async_session_maker() as session:
        existing = await session.execute(select(User).where(User.email == AUTH_DEFAULT_ADMIN_EMAIL))
        if existing.scalar_one_or_none() is not None:
            return

    user_create = UserCreate(
        email=AUTH_DEFAULT_ADMIN_EMAIL,
        password=AUTH_DEFAULT_ADMIN_PASSWORD,
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )

    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        await manager.create(user_create, safe=False)
