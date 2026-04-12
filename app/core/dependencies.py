from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientPermissionsException
from app.domain.entities.user import User, UserRole
from app.domain.repositories.token_repository import AbstractTokenRepository
from app.infrastructure.cache.redis_token_repository import RedisTokenRepository
from app.infrastructure.cache.token_cache import TokenCache, get_redis_client
from app.infrastructure.database.audit_repository import SQLAuditRepository
from app.infrastructure.database.session import get_db
from app.infrastructure.database.user_repository import SQLUserRepository
from app.services.audit_service import AuditLogService
from app.services.auth_service import AuthService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/form")


# ------------------------------------------------------------------ #
#  Infrastructure factories                                            #
# ------------------------------------------------------------------ #

def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLUserRepository:
    return SQLUserRepository(session)


def get_audit_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SQLAuditRepository:
    return SQLAuditRepository(session)


async def get_token_repository() -> AbstractTokenRepository:
    """Provides RedisTokenRepository (JWT JTI store + denylist)."""
    client = await get_redis_client()
    return RedisTokenRepository(client)


async def get_token_cache() -> TokenCache:
    """Provides TokenCache (raw-key store for email verify + pwd reset)."""
    client = await get_redis_client()
    return TokenCache(client)


# ------------------------------------------------------------------ #
#  Service factories                                                   #
# ------------------------------------------------------------------ #

def get_auth_service(
    user_repo:  Annotated[SQLUserRepository,       Depends(get_user_repository)],
    token_repo: Annotated[AbstractTokenRepository, Depends(get_token_repository)],
) -> AuthService:
    return AuthService(user_repo=user_repo, token_repo=token_repo)


def get_user_service(
    repo:  Annotated[SQLUserRepository, Depends(get_user_repository)],
    cache: Annotated[TokenCache,         Depends(get_token_cache)],
) -> UserService:
    return UserService(user_repo=repo, token_cache=cache)


def get_audit_service(
    repo: Annotated[SQLAuditRepository, Depends(get_audit_repository)],
) -> AuditLogService:
    return AuditLogService(repo=repo)


# ------------------------------------------------------------------ #
#  Auth guards                                                         #
# ------------------------------------------------------------------ #

async def get_current_user(
    token:        Annotated[str,         Depends(oauth2_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    return await auth_service.get_current_user(access_token=token)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


def require_roles(*roles: UserRole):
    async def _guard(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if not current_user.has_role(*roles):
            raise InsufficientPermissionsException(required_role=", ".join(roles))
        return current_user
    return _guard


# ------------------------------------------------------------------ #
#  Convenience type aliases                                            #
# ------------------------------------------------------------------ #

CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser   = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
