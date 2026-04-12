"""
Repository and Service Factories.

This module contains dependency factories for repositories and services.
All factories return abstract types, ensuring loose coupling and easy testing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.audit_repository import AbstractAuditRepository
from app.domain.repositories.token_cache import AbstractTokenCache
from app.domain.repositories.token_repository import AbstractTokenRepository
from app.domain.repositories.user_repository import AbstractUserRepository
from app.infrastructure.cache.redis_token_repository import RedisTokenRepository
from app.infrastructure.cache.token_cache import TokenCache, get_redis_client
from app.infrastructure.database.audit_repository import SQLAuditRepository
from app.infrastructure.database.session import get_db
from app.infrastructure.database.user_repository import SQLUserRepository
from app.services.audit_service import AuditLogService
from app.services.auth_service import AuthService
from app.services.user_service import UserService

# ================================================================ #
#  Repository Factories (Infrastructure)                           #
# ================================================================ #


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AbstractUserRepository:
    """
    Factory for user repository.
    Returns abstract type to decouple from SQLAlchemy implementation.
    """
    return SQLUserRepository(session)


def get_audit_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AbstractAuditRepository:
    """
    Factory for audit repository.
    Returns abstract type to decouple from SQLAlchemy implementation.
    """
    return SQLAuditRepository(session)


async def get_token_repository() -> AbstractTokenRepository:
    """
    Factory for token repository (JWT JTI store + denylist).
    Returns abstract type to decouple from Redis implementation.
    """
    client = await get_redis_client()
    return RedisTokenRepository(client)


async def get_token_cache() -> AbstractTokenCache:
    """
    Factory for token cache (temporary tokens: email verify, password reset).
    Returns abstract type to decouple from Redis implementation.
    """
    client = await get_redis_client()
    return TokenCache(client)


# ================================================================ #
#  Service Factories (Application Layer)                           #
# ================================================================ #


def get_auth_service(
    user_repo: Annotated[AbstractUserRepository, Depends(get_user_repository)],
    token_repo: Annotated[AbstractTokenRepository, Depends(get_token_repository)],
) -> AuthService:
    """Factory for authentication service."""
    return AuthService(user_repo=user_repo, token_repo=token_repo)


def get_user_service(
    repo: Annotated[AbstractUserRepository, Depends(get_user_repository)],
    cache: Annotated[AbstractTokenCache, Depends(get_token_cache)],
) -> UserService:
    """Factory for user service (profile, password, email verification)."""
    return UserService(user_repo=repo, token_cache=cache)


def get_audit_service(
    repo: Annotated[AbstractAuditRepository, Depends(get_audit_repository)],
) -> AuditLogService:
    """Factory for audit logging service."""
    return AuditLogService(repo=repo)
