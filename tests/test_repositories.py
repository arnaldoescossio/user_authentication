"""
Unit tests for the concrete repository implementations.
Uses an in-memory SQLite engine — no Postgres needed.

Covers:
  - SQLUserRepository: all CRUD operations
  - SQLAuditRepository: append + list + filter
  - RedisTokenRepository: logic tested via FakeTokenRepo in test_auth.py
"""
from __future__ import annotations

import uuid
from datetime import datetime, UTC

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.entities.user import User, UserRole, UserStatus
from app.domain.repositories.audit_repository import AuditFilter
from app.infrastructure.database.audit_models import AuditEvent, AuditLogORM
from app.infrastructure.database.audit_repository import SQLAuditRepository
from app.infrastructure.database.models import Base, UserORM
from app.infrastructure.database.user_repository import SQLUserRepository
from app.infrastructure.security.password import hash_password

# ------------------------------------------------------------------ #
#  Shared SQLite fixture                                               #
# ------------------------------------------------------------------ #

_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(lambda c: AuditLogORM.__table__.create(c, checkfirst=True))
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with _Session() as s:
        yield s
        await s.rollback()   # isolate each test


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def make_user(email: str = "u@example.com", username: str = "user1") -> User:
    return User(
        email=email,
        username=username,
        hashed_password=hash_password("Pass123"),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )


# ------------------------------------------------------------------ #
#  SQLUserRepository                                                   #
# ------------------------------------------------------------------ #

class TestSQLUserRepository:

    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, session):
        repo = SQLUserRepository(session)
        user = await repo.create(make_user(email="a@x.com", username="aaa"))
        await session.flush()

        found = await repo.get_by_id(user.id)
        assert found is not None
        assert found.email == "a@x.com"

    @pytest.mark.asyncio
    async def test_get_by_email_case_insensitive(self, session):
        repo = SQLUserRepository(session)
        await repo.create(make_user(email="b@x.com", username="bbb"))
        await session.flush()

        found = await repo.get_by_email("B@x.com")
        assert found is not None
        assert found.username == "bbb"

    @pytest.mark.asyncio
    async def test_get_by_username(self, session):
        repo = SQLUserRepository(session)
        await repo.create(make_user(email="c@x.com", username="ccc"))
        await session.flush()

        found = await repo.get_by_username("ccc")
        assert found is not None
        assert found.email == "c@x.com"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found_returns_none(self, session):
        repo = SQLUserRepository(session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_exists_by_email_true(self, session):
        repo = SQLUserRepository(session)
        await repo.create(make_user(email="d@x.com", username="ddd"))
        await session.flush()
        assert await repo.exists_by_email("d@x.com") is True

    @pytest.mark.asyncio
    async def test_exists_by_email_false(self, session):
        repo = SQLUserRepository(session)
        assert await repo.exists_by_email("nobody@x.com") is False

    @pytest.mark.asyncio
    async def test_update_fields(self, session):
        repo = SQLUserRepository(session)
        user = await repo.create(make_user(email="e@x.com", username="eee"))
        await session.flush()

        updated = user.model_copy(update={"full_name": "Eve", "role": UserRole.MODERATOR})
        saved = await repo.update(updated)
        assert saved.full_name == "Eve"
        assert saved.role == UserRole.MODERATOR

    @pytest.mark.asyncio
    async def test_delete(self, session):
        repo = SQLUserRepository(session)
        user = await repo.create(make_user(email="f@x.com", username="fff"))
        await session.flush()

        await repo.delete(user.id)
        await session.flush()
        assert await repo.get_by_id(user.id) is None

    @pytest.mark.asyncio
    async def test_domain_entity_never_exposes_orm(self, session):
        """Returned object must be a domain User, not a SQLAlchemy ORM instance."""
        repo   = SQLUserRepository(session)
        user   = await repo.create(make_user(email="g@x.com", username="ggg"))
        assert isinstance(user, User)
        assert not isinstance(user, UserORM)


# ------------------------------------------------------------------ #
#  SQLAuditRepository                                                  #
# ------------------------------------------------------------------ #

class TestSQLAuditRepository:

    @pytest.mark.asyncio
    async def test_append_returns_uuid(self, session):
        repo = SQLAuditRepository(session)
        entry_id = await repo.append(
            event_type=AuditEvent.USER_REGISTERED,
            actor_id=uuid.uuid4(),
            ip_address="127.0.0.1",
        )
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_get_by_id(self, session):
        repo     = SQLAuditRepository(session)
        actor_id = uuid.uuid4()
        eid      = await repo.append(
            event_type=AuditEvent.USER_LOGIN_SUCCESS,
            actor_id=actor_id,
        )
        await session.flush()

        row = await repo.get_by_id(eid)
        assert row is not None
        assert row.actor_id == actor_id
        assert row.event_type == AuditEvent.USER_LOGIN_SUCCESS

    @pytest.mark.asyncio
    async def test_list_no_filter(self, session):
        repo = SQLAuditRepository(session)
        for _ in range(3):
            await repo.append(event_type=AuditEvent.TOKEN_REFRESHED)
        await session.flush()

        rows, total = await repo.list()
        assert total >= 3

    @pytest.mark.asyncio
    async def test_list_filter_by_actor(self, session):
        repo     = SQLAuditRepository(session)
        actor_id = uuid.uuid4()
        await repo.append(event_type=AuditEvent.USER_LOGOUT, actor_id=actor_id)
        await repo.append(event_type=AuditEvent.USER_LOGOUT, actor_id=uuid.uuid4())
        await session.flush()

        rows, total = await repo.list(filters=AuditFilter(actor_id=actor_id))
        assert all(r.actor_id == actor_id for r in rows)

    @pytest.mark.asyncio
    async def test_list_filter_by_event_type(self, session):
        repo = SQLAuditRepository(session)
        await repo.append(event_type=AuditEvent.PASSWORD_CHANGED)
        await repo.append(event_type=AuditEvent.EMAIL_VERIFIED)
        await session.flush()

        rows, total = await repo.list(
            filters=AuditFilter(event_type=AuditEvent.PASSWORD_CHANGED)
        )
        assert all(r.event_type == AuditEvent.PASSWORD_CHANGED for r in rows)

    @pytest.mark.asyncio
    async def test_list_pagination(self, session):
        repo = SQLAuditRepository(session)
        for _ in range(5):
            await repo.append(event_type=AuditEvent.TOKEN_REFRESHED)
        await session.flush()

        rows, total = await repo.list(offset=0, limit=2)
        assert len(rows) <= 2

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, session):
        repo   = SQLAuditRepository(session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None
