from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings


class TokenCache:
    """
    Redis-backed token cache.

    Responsibilities:
    - Store refresh tokens (jti → user_id) for rotation / revocation.
    - Maintain a denylist for revoked access tokens (jti → "revoked").
    """

    _REFRESH_PREFIX = "refresh:"
    _DENYLIST_PREFIX = "denylist:"

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    # ------------------------------------------------------------------ #
    #  Refresh tokens                                                      #
    # ------------------------------------------------------------------ #

    async def store_refresh_token(
        self,
        jti: str,
        user_id: str,
        ttl_seconds: int,
    ) -> None:
        """Persist a refresh token JTI → user_id mapping with TTL."""
        key = f"{self._REFRESH_PREFIX}{jti}"
        await self._client.setex(key, ttl_seconds, user_id)

    async def get_refresh_token_owner(self, jti: str) -> str | None:
        """Return the user_id owning this refresh token, or None if not found."""
        key = f"{self._REFRESH_PREFIX}{jti}"
        value = await self._client.get(key)
        return value.decode() if value else None

    async def revoke_refresh_token(self, jti: str) -> None:
        """Delete a refresh token (used after rotation or logout)."""
        await self._client.delete(f"{self._REFRESH_PREFIX}{jti}")

    # ------------------------------------------------------------------ #
    #  Access token denylist                                               #
    # ------------------------------------------------------------------ #

    async def deny_access_token(self, jti: str, ttl_seconds: int) -> None:
        """Add a JTI to the denylist until its natural expiry."""
        key = f"{self._DENYLIST_PREFIX}{jti}"
        await self._client.setex(key, ttl_seconds, "revoked")

    async def is_access_token_denied(self, jti: str) -> bool:
        """Return True if the token's JTI is on the denylist."""
        key = f"{self._DENYLIST_PREFIX}{jti}"
        return await self._client.exists(key) == 1


# ------------------------------------------------------------------ #
#  Singleton / factory                                                 #
# ------------------------------------------------------------------ #

_redis_client: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
    return _redis_client


async def get_token_cache() -> TokenCache:
    """FastAPI dependency for TokenCache."""
    client = await get_redis_client()
    return TokenCache(client)
