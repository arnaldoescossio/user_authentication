from __future__ import annotations

import time

import redis.asyncio as aioredis
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.infrastructure.cache.token_cache import get_redis_client


class RateLimitConfig:
    """Per-route sliding-window rate-limit config."""

    def __init__(self, requests: int, window_seconds: int) -> None:
        self.requests       = requests
        self.window_seconds = window_seconds


# Route-level overrides — applied by prefix match (longest wins)
_ROUTE_LIMITS: dict[str, RateLimitConfig] = {
    "/api/v1/auth/login":    RateLimitConfig(requests=10,  window_seconds=60),
    "/api/v1/auth/register": RateLimitConfig(requests=5,   window_seconds=60),
    "/api/v1/auth/refresh":  RateLimitConfig(requests=30,  window_seconds=60),
    "/api/v1/auth/logout":   RateLimitConfig(requests=20,  window_seconds=60),
}

_DEFAULT_LIMIT = RateLimitConfig(requests=120, window_seconds=60)

# Paths exempt from rate limiting (e.g. health checks)
_EXEMPT_PREFIXES = {"/health", "/docs", "/redoc", "/openapi.json"}


def _resolve_limit(path: str) -> RateLimitConfig:
    # Longest matching prefix wins
    match = max(
        (prefix for prefix in _ROUTE_LIMITS if path.startswith(prefix)),
        key=len,
        default=None,
    )
    return _ROUTE_LIMITS[match] if match else _DEFAULT_LIMIT


def _client_key(request: Request) -> str:
    """Derive the rate-limit key from the real client IP."""
    forwarded_for = request.headers.get("x-forwarded-for")
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    return ip


class SlidingWindowRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis sliding-window rate limiter.

    Uses a sorted set per (ip, route) where each member is a request
    timestamp (float). On each request:
      1. Remove timestamps older than now - window_seconds.
      2. Count remaining entries.
      3. If count >= limit → 429.
      4. Otherwise, add current timestamp and set TTL.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Exempt certain paths
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        config = _resolve_limit(path)
        client = _client_key(request)
        redis: aioredis.Redis = await get_redis_client()

        key  = f"rl:{client}:{path}"
        now  = time.time()
        cutoff = now - config.window_seconds

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, config.window_seconds)
        _, count, *_ = await pipe.execute()

        remaining = max(0, config.requests - int(count) - 1)
        reset_at  = int(now) + config.window_seconds

        headers = {
            "X-RateLimit-Limit":     str(config.requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset":     str(reset_at),
        }

        if int(count) >= config.requests:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": config.window_seconds,
                },
                headers={**headers, "Retry-After": str(config.window_seconds)},
            )

        response = await call_next(request)
        for header, value in headers.items():
            response.headers[header] = value
        return response
