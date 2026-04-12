from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.exceptions import (
    CredentialsException,
    InactiveUserException,
    TokenRevokedException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from app.domain.entities.user import User, UserRole
from app.domain.repositories.token_repository import AbstractTokenRepository
from app.domain.repositories.user_repository import AbstractUserRepository
from app.infrastructure.security.jwt import jwt_service
from app.infrastructure.security.password import hash_password, verify_password


@dataclass
class TokenPair:
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class AuthService:
    """
    Orchestrates authentication flows.
    Depends on AbstractUserRepository and AbstractTokenRepository (ports),
    never on concrete infrastructure classes.
    """

    def __init__(
        self,
        user_repo:  AbstractUserRepository,
        token_repo: AbstractTokenRepository,
    ) -> None:
        self._users  = user_repo
        self._tokens = token_repo

    # ------------------------------------------------------------------ #
    #  Register                                                            #
    # ------------------------------------------------------------------ #

    async def register(
        self,
        *,
        email:     str,
        username:  str,
        password:  str,
        full_name: str | None = None,
        role:      UserRole   = UserRole.USER,
    ) -> User:
        if await self._users.exists_by_email(email):
            raise UserAlreadyExistsException(email)

        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )
        return await self._users.create(user)

    # ------------------------------------------------------------------ #
    #  Login                                                               #
    # ------------------------------------------------------------------ #

    async def login(self, *, email: str, password: str) -> TokenPair:
        user = await self._users.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise CredentialsException("Invalid email or password.")
        if not user.is_active:
            raise InactiveUserException()
        return await self._issue_pair(user)

    # ------------------------------------------------------------------ #
    #  Refresh (with rotation)                                             #
    # ------------------------------------------------------------------ #

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        payload  = jwt_service.decode_refresh_token(refresh_token)
        jti:     str = payload["jti"]
        user_id: str = payload["sub"]

        stored = await self._tokens.get_refresh_owner(jti)
        if stored is None or stored != user_id:
            raise TokenRevokedException()

        # Rotate: delete old JTI before issuing new one
        await self._tokens.revoke_refresh(jti)

        user = await self._users.get_by_id(uuid.UUID(user_id))
        if not user:
            raise UserNotFoundException(user_id)
        if not user.is_active:
            raise InactiveUserException()

        return await self._issue_pair(user)

    # ------------------------------------------------------------------ #
    #  Logout                                                              #
    # ------------------------------------------------------------------ #

    async def logout(
        self,
        *,
        access_jti:    str,
        refresh_token: str | None = None,
    ) -> None:
        await self._tokens.deny_access(
            access_jti,
            ttl_seconds=jwt_service.access_token_ttl_seconds,
        )
        if refresh_token:
            try:
                payload = jwt_service.decode_refresh_token(refresh_token)
                await self._tokens.revoke_refresh(payload["jti"])
            except Exception:
                pass  # best-effort; access already denied

    async def logout_all_devices(self, *, user_id: str, access_jti: str) -> None:
        """Force-sign-out all sessions (e.g. after password reset or ban)."""
        await self._tokens.deny_access(
            access_jti,
            ttl_seconds=jwt_service.access_token_ttl_seconds,
        )
        await self._tokens.revoke_all_refresh_for_user(user_id)

    # ------------------------------------------------------------------ #
    #  Current-user resolution (used by FastAPI dependency)               #
    # ------------------------------------------------------------------ #

    async def get_current_user(self, *, access_token: str) -> User:
        payload  = jwt_service.decode_access_token(access_token)
        jti:     str = payload["jti"]
        user_id: str = payload["sub"]

        if await self._tokens.is_access_denied(jti):
            raise TokenRevokedException()

        user = await self._users.get_by_id(uuid.UUID(user_id))
        if not user:
            raise UserNotFoundException(user_id)
        if not user.is_active:
            raise InactiveUserException()

        return user

    # ------------------------------------------------------------------ #
    #  Private                                                             #
    # ------------------------------------------------------------------ #

    async def _issue_pair(self, user: User) -> TokenPair:
        access_token,  _           = jwt_service.create_access_token(str(user.id), user.role)
        refresh_token, refresh_jti = jwt_service.create_refresh_token(str(user.id))

        await self._tokens.store_refresh(
            jti=refresh_jti,
            user_id=str(user.id),
            ttl_seconds=jwt_service.refresh_token_ttl_seconds,
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token)
