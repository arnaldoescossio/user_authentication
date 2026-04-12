"""
Test fixtures — async httpx client with overridden DB and token repository.

Infrastructure overrides:
  - get_db          → SQLite in-memory (no Postgres needed)
  - get_token_repository → FakeTokenRepository (no Redis needed)
  - get_token_cache      → FakeTokenCache (for email/reset tokens)
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.repositories.token_repository import AbstractTokenRepository
from app.infrastructure.cache.token_cache import TokenCache
from app.infrastructure.database.models import Base
from app.infrastructure.database.audit_models import AuditLogORM
from app.infrastructure.database.session import get_db
from app.core.dependencies import get_token_repository, get_token_cache
from app.main import create_app

# ------------------------------------------------------------------ #
#  In-memory SQLite                                                    #
# ------------------------------------------------------------------ #

_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


# ------------------------------------------------------------------ #
#  Fake token repository (no Redis)                                   #
# ------------------------------------------------------------------ #

class FakeTokenRepository(AbstractTokenRepository):
    def __init__(self) -> None:
        self._refresh: dict[str, str] = {}           # jti → user_id
        self._user_jtis: dict[str, set] = {}         # user_id → {jti}
        self._denied:  set[str]         = set()

    async def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        self._refresh[jti] = user_id
        self._user_jtis.setdefault(user_id, set()).add(jti)

    async def get_refresh_owner(self, jti: str) -> str | None:
        return self._refresh.get(jti)

    async def revoke_refresh(self, jti: str) -> None:
        owner = self._refresh.pop(jti, None)
        if owner:
            self._user_jtis.get(owner, set()).discard(jti)

    async def revoke_all_refresh_for_user(self, user_id: str) -> None:
        for jti in list(self._user_jtis.get(user_id, set())):
            self._refresh.pop(jti, None)
        self._user_jtis.pop(user_id, None)

    async def deny_access(self, jti: str, ttl_seconds: int) -> None:
        self._denied.add(jti)

    async def is_access_denied(self, jti: str) -> bool:
        return jti in self._denied


# ------------------------------------------------------------------ #
#  Fake token cache (for email/reset tokens)                          #
# ------------------------------------------------------------------ #

class _FakeRedisClient:
    def __init__(self, store: dict) -> None:
        self._s = store

    async def setex(self, key, ttl, value):
        self._s[key] = value if isinstance(value, str) else value.decode()

    async def get(self, key):
        v = self._s.get(key)
        return v.encode() if isinstance(v, str) else v

    async def delete(self, key):
        self._s.pop(key, None)


class FakeTokenCache(TokenCache):
    def __init__(self) -> None:
        self._store: dict = {}
        self._client = _FakeRedisClient(self._store)

    async def store_refresh_token(self, jti, user_id, ttl_seconds): pass
    async def get_refresh_token_owner(self, jti): return None
    async def revoke_refresh_token(self, jti): pass
    async def deny_access_token(self, jti, ttl_seconds): pass
    async def is_access_token_denied(self, jti): return False


# ------------------------------------------------------------------ #
#  Session-scoped table creation                                       #
# ------------------------------------------------------------------ #

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Also create audit_logs table
        from sqlalchemy import inspect
        await conn.run_sync(
            lambda c: AuditLogORM.__table__.create(c, checkfirst=True)
        )
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ------------------------------------------------------------------ #
#  Per-test async client                                               #
# ------------------------------------------------------------------ #

@pytest_asyncio.fixture
async def fake_token_repo() -> FakeTokenRepository:
    return FakeTokenRepository()


@pytest_asyncio.fixture
async def async_client(fake_token_repo: FakeTokenRepository) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with _Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fake_cache = FakeTokenCache()

    app.dependency_overrides[get_db]               = _override_db
    app.dependency_overrides[get_token_repository] = lambda: fake_token_repo
    app.dependency_overrides[get_token_cache]      = lambda: fake_cache

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ------------------------------------------------------------------ #
#  User helpers                                                        #
# ------------------------------------------------------------------ #

@pytest_asyncio.fixture
async def registered_user(async_client: AsyncClient) -> dict[str, Any]:
    resp = await async_client.post("/api/v1/auth/register", json={
        "email": "testuser@example.com", "username": "testuser", "password": "Secret123",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, registered_user) -> dict[str, str]:
    resp = await async_client.post("/api/v1/auth/login", json={
        "email": "testuser@example.com", "password": "Secret123",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_user_and_headers(async_client: AsyncClient) -> dict[str, Any]:
    resp = await async_client.post("/api/v1/auth/register", json={
        "email": "admin@example.com", "username": "adminuser", "password": "Admin1234",
    })
    assert resp.status_code == 201, resp.text

    async with _Session() as s:
        from sqlalchemy import update
        from app.infrastructure.database.models import UserORM
        from app.domain.entities.user import UserRole
        await s.execute(
            update(UserORM).where(UserORM.email == "admin@example.com")
            .values(role=UserRole.ADMIN)
        )
        await s.commit()

    login = await async_client.post("/api/v1/auth/login", json={
        "email": "admin@example.com", "password": "Admin1234",
    })
    assert login.status_code == 200
    return {
        "user":    resp.json(),
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }
