from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractTokenRepository(ABC):
    """
    Port (interface) for token-state persistence.

    Separates the concept of *token storage* from any concrete
    backend (Redis, Memcached, in-memory, DB).

    Two responsibilities:
      1. Refresh-token registry  — JTI → owner_user_id with TTL
      2. Access-token denylist   — revoked JTIs with TTL
    """

    # ------------------------------------------------------------------ #
    #  Refresh tokens                                                      #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def store_refresh(
        self,
        jti:         str,
        user_id:     str,
        ttl_seconds: int,
    ) -> None:
        """Persist refresh-token JTI → user_id with a TTL."""
        ...

    @abstractmethod
    async def get_refresh_owner(self, jti: str) -> str | None:
        """Return the user_id owning this refresh JTI, or None if absent/expired."""
        ...

    @abstractmethod
    async def revoke_refresh(self, jti: str) -> None:
        """Remove a refresh-token JTI (rotation, logout)."""
        ...

    @abstractmethod
    async def revoke_all_refresh_for_user(self, user_id: str) -> None:
        """
        Revoke every refresh token belonging to this user.
        Used when an admin bans a user or forces a full sign-out.
        Implementations may use a user-keyed set to track per-user JTIs.
        """
        ...

    # ------------------------------------------------------------------ #
    #  Access-token denylist                                               #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def deny_access(self, jti: str, ttl_seconds: int) -> None:
        """Add an access-token JTI to the denylist until it naturally expires."""
        ...

    @abstractmethod
    async def is_access_denied(self, jti: str) -> bool:
        """Return True if this access-token JTI is on the denylist."""
        ...
