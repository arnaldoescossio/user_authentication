from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from app.core.exceptions import CredentialsException, UserNotFoundException
from app.domain.entities.user import User, UserRole, UserStatus
from app.domain.repositories.token_cache import AbstractTokenCache
from app.domain.repositories.user_repository import AbstractUserRepository
from app.infrastructure.security.password import hash_password, verify_password

_VERIFY_PREFIX = "email_verify:"
_RESET_PREFIX = "pwd_reset:"
_VERIFY_TTL = int(timedelta(hours=24).total_seconds())
_RESET_TTL = int(timedelta(hours=1).total_seconds())


class UserService:
    """
    Handles user-centric operations that are not strictly about token issuance:
      - profile updates (own or admin)
      - password change
      - email-verification token generation / confirmation
      - password-reset token generation / confirmation
      - soft-delete / ban / activate
    """

    def __init__(
        self,
        user_repo: AbstractUserRepository,
        token_cache: AbstractTokenCache,
    ) -> None:
        self._repo = user_repo
        self._cache = token_cache

    # ------------------------------------------------------------------ #
    #  Profile                                                             #
    # ------------------------------------------------------------------ #

    async def update_profile(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None = None,
        username: str | None = None,
    ) -> User:
        user = await self._get_or_404(user_id)
        changes: dict = {}
        if full_name is not None:
            changes["full_name"] = full_name
        if username is not None:
            changes["username"] = username
        if not changes:
            return user
        updated = user.model_copy(update=changes)
        return await self._repo.update(updated)

    # ------------------------------------------------------------------ #
    #  Password                                                            #
    # ------------------------------------------------------------------ #

    async def change_password(
        self,
        *,
        user_id: uuid.UUID,
        current_password: str,
        new_password: str,
    ) -> None:
        user = await self._get_or_404(user_id)
        if not verify_password(current_password, user.hashed_password):
            raise CredentialsException("Current password is incorrect.")
        updated = user.model_copy(
            update={"hashed_password": hash_password(new_password)}
        )
        await self._repo.update(updated)

    # ------------------------------------------------------------------ #
    #  Email verification                                                  #
    # ------------------------------------------------------------------ #

    async def generate_verification_token(self, user_id: uuid.UUID) -> str:
        """
        Create a secure random token, store it in Redis, return it.
        The caller is responsible for delivering it (e.g. via email).
        """
        token = secrets.token_urlsafe(32)
        key = f"{_VERIFY_PREFIX}{token}"
        await self._cache._client.setex(key, _VERIFY_TTL, str(user_id))
        return token

    async def confirm_email(self, token: str) -> User:
        key = f"{_VERIFY_PREFIX}{token}"
        raw = await self._cache._client.get(key)
        if not raw:
            raise CredentialsException("Verification token is invalid or has expired.")

        user_id = uuid.UUID(raw.decode())
        await self._cache._client.delete(key)

        user = await self._get_or_404(user_id)
        updated = user.model_copy(update={"is_verified": True})
        return await self._repo.update(updated)

    # ------------------------------------------------------------------ #
    #  Password reset                                                      #
    # ------------------------------------------------------------------ #

    async def generate_password_reset_token(self, email: str) -> str | None:
        """
        Return a reset token for the given email, or None if email not found.
        Returning None (instead of raising) prevents email-enumeration attacks.
        """
        user = await self._repo.get_by_email(email)
        if not user:
            return None
        token = secrets.token_urlsafe(32)
        key = f"{_RESET_PREFIX}{token}"
        await self._cache._client.setex(key, _RESET_TTL, str(user.id))
        return token

    async def reset_password(self, *, token: str, new_password: str) -> None:
        key = f"{_RESET_PREFIX}{token}"
        raw = await self._cache._client.get(key)
        if not raw:
            raise CredentialsException("Reset token is invalid or has expired.")

        user_id = uuid.UUID(raw.decode())
        await self._cache._client.delete(key)

        user = await self._get_or_404(user_id)
        updated = user.model_copy(
            update={"hashed_password": hash_password(new_password)}
        )
        await self._repo.update(updated)

    # ------------------------------------------------------------------ #
    #  Admin status management                                            #
    # ------------------------------------------------------------------ #

    async def set_status(self, *, user_id: uuid.UUID, status: UserStatus) -> User:
        user = await self._get_or_404(user_id)
        updated = user.model_copy(update={"status": status})
        return await self._repo.update(updated)

    async def set_role(self, *, user_id: uuid.UUID, role: UserRole) -> User:
        user = await self._get_or_404(user_id)
        updated = user.model_copy(update={"role": role})
        return await self._repo.update(updated)

    # ------------------------------------------------------------------ #
    #  Private                                                             #
    # ------------------------------------------------------------------ #

    async def _get_or_404(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundException(str(user_id))
        return user
