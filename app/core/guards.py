"""
Authentication Guards and Authorization.

This module contains auth guards and role-based access control (RBAC) logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.exceptions import InsufficientPermissionsException
from app.core.factories import get_auth_service
from app.core.security import oauth2_scheme
from app.domain.entities.user import User, UserRole
from app.services.auth_service import AuthService

# ================================================================ #
#  Auth Guards                                                     #
# ================================================================ #


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Guard: Extract and validate bearer token.
    Returns the authenticated user.
    """
    return await auth_service.get_current_user(access_token=token)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Guard: Ensure the current user is active.
    Returns the active user.
    """
    return current_user


def require_roles(*roles: UserRole):
    """
    Guard factory: Require specific roles.
    Returns a guard function for the given roles.
    """

    async def _guard(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if not current_user.has_role(*roles):
            raise InsufficientPermissionsException(required_role=", ".join(roles))
        return current_user

    return _guard


# ================================================================ #
#  Convenience Type Aliases                                        #
# ================================================================ #

CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
