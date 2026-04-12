from __future__ import annotations

import redis.asyncio as aioredis

from app.domain.repositories.token_repository import AbstractTokenRepository

_REFRESH_PREFIX  = "rt:"       # rt:<jti>            → user_id
_USER_JTIS_PREFIX = "u_rt:"   # u_rt:<user_id>       → SET of active JTIs
_DENYLIST_PREFIX = "dl:"       # dl:<jti>             → "1"


class RedisTokenRepository(AbstractTokenRepository):
    """
    Redis-backed token repository.

    Key schema
    ----------
    rt:<jti>          STRING  user_id             TTL = refresh token lifetime
    u_rt:<user_id>    SET     {jti, jti, …}       No TTL (cleaned on revoke)
    dl:<jti>          STRING  "1"                 TTL = remaining access token lifetime
    """

    def __init__(self, client: aioredis.Redis) -> None:
        self._r = client

    # ------------------------------------------------------------------ #
    #  Refresh tokens                                                      #
    # ------------------------------------------------------------------ #

    async def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        pipe = self._r.pipeline()
        pipe.setex(f"{_REFRESH_PREFIX}{jti}", ttl_seconds, user_id)
        pipe.sadd(f"{_USER_JTIS_PREFIX}{user_id}", jti)
        pipe.expire(f"{_USER_JTIS_PREFIX}{user_id}", ttl_seconds)
        await pipe.execute()

    async def get_refresh_owner(self, jti: str) -> str | None:
        raw = await self._r.get(f"{_REFRESH_PREFIX}{jti}")
        return raw.decode() if raw else None

    async def revoke_refresh(self, jti: str) -> None:
        # Fetch owner first so we can remove jti from the user set
        owner = await self.get_refresh_owner(jti)
        pipe  = self._r.pipeline()
        pipe.delete(f"{_REFRESH_PREFIX}{jti}")
        if owner:
            pipe.srem(f"{_USER_JTIS_PREFIX}{owner}", jti)
        await pipe.execute()

    async def revoke_all_refresh_for_user(self, user_id: str) -> None:
        """
        Atomically fetch every JTI belonging to the user and delete them all.
        Uses a pipeline to minimise round-trips.
        """
        user_key = f"{_USER_JTIS_PREFIX}{user_id}"
        jtis: set[bytes] = await self._r.smembers(user_key)

        if not jtis:
            return

        pipe = self._r.pipeline()
        for raw_jti in jtis:
            pipe.delete(f"{_REFRESH_PREFIX}{raw_jti.decode()}")
        pipe.delete(user_key)
        await pipe.execute()

    # ------------------------------------------------------------------ #
    #  Access-token denylist                                               #
    # ------------------------------------------------------------------ #

    async def deny_access(self, jti: str, ttl_seconds: int) -> None:
        await self._r.setex(f"{_DENYLIST_PREFIX}{jti}", ttl_seconds, "1")

    async def is_access_denied(self, jti: str) -> bool:
        return await self._r.exists(f"{_DENYLIST_PREFIX}{jti}") == 1
