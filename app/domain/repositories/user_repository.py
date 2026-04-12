from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.domain.entities.user import User


class AbstractUserRepository(ABC):
    """Port (interface) for user persistence — no infrastructure details."""

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool: ...
