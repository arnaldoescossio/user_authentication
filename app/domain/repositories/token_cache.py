from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractTokenCache(ABC):
    """
    Port (interface) for token storage — no infrastructure details.

    Responsibilities:
    - Store refresh tokens (jti → user_id) for rotation / revocation.
    - Maintain a denylist for revoked access tokens (jti → "revoked").
    - Store temporary verification/reset tokens.
    """

    @abstractmethod
    async def store_refresh_token(
        self,
        jti: str,
        user_id: str,
        ttl_seconds: int,
    ) -> None:
        """Persist a refresh token JTI → user_id mapping with TTL."""
        ...

    @abstractmethod
    async def get_refresh_token_owner(self, jti: str) -> str | None:
        """Return the user_id owning this refresh token, or None if not found."""
        ...

    @abstractmethod
    async def revoke_refresh_token(self, jti: str) -> None:
        """Delete a refresh token (used after rotation or logout)."""
        ...

    @abstractmethod
    async def deny_access_token(self, jti: str, ttl_seconds: int) -> None:
        """Add a JTI to the denylist until its natural expiry."""
        ...

    @abstractmethod
    async def is_access_token_denied(self, jti: str) -> bool:
        """Return True if the token's JTI is on the denylist."""
        ...

    @abstractmethod
    async def set_temporary_token(
        self,
        prefix: str,
        token: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        """Store a temporary token (email verification, password reset, etc)."""
        ...

    @abstractmethod
    async def get_temporary_token(self, prefix: str, token: str) -> str | None:
        """Retrieve a temporary token value, or None if not found or expired."""
        ...

    @abstractmethod
    async def delete_temporary_token(self, prefix: str, token: str) -> None:
        """Delete a temporary token."""
        ...
