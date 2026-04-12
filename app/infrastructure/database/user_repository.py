from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.domain.repositories.user_repository import AbstractUserRepository
from app.infrastructure.database.models import UserORM


class SQLUserRepository(AbstractUserRepository):
    """
    Concrete SQLAlchemy 2.0 async implementation of AbstractUserRepository.
    Translates between ORM rows and domain User entities.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    #  Mapping helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_domain(orm: UserORM) -> User:
        return User.model_validate(orm)

    @staticmethod
    def _to_orm(user: User) -> UserORM:
        return UserORM(
            id=user.id,
            email=user.email,
            username=user.username,
            hashed_password=user.hashed_password,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    # ------------------------------------------------------------------ #
    #  CRUD                                                                #
    # ------------------------------------------------------------------ #

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(UserORM).where(UserORM.id == user_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserORM).where(UserORM.email == email.lower())
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(UserORM).where(UserORM.username == username.lower())
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm else None

    async def create(self, user: User) -> User:
        orm = self._to_orm(user)
        self._session.add(orm)
        await self._session.flush()          # flush to get DB-generated fields
        await self._session.refresh(orm)
        return self._to_domain(orm)

    async def update(self, user: User) -> User:
        stmt = select(UserORM).where(UserORM.id == user.id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one()

        orm.email = user.email
        orm.username = user.username
        orm.hashed_password = user.hashed_password
        orm.full_name = user.full_name
        orm.role = user.role
        orm.status = user.status
        orm.is_verified = user.is_verified

        await self._session.flush()
        await self._session.refresh(orm)
        return self._to_domain(orm)

    async def delete(self, user_id: uuid.UUID) -> None:
        stmt = select(UserORM).where(UserORM.id == user_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one()
        await self._session.delete(orm)
        await self._session.flush()

    async def exists_by_email(self, email: str) -> bool:
        stmt = select(UserORM.id).where(UserORM.email == email.lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
