"""
Health check endpoint with real dependency probing.

GET /health        — lightweight liveness (always fast)
GET /health/ready  — readiness: probes Postgres + Redis (used by k8s readiness probe)
"""
# from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.infrastructure.cache.token_cache import get_redis_client
from app.infrastructure.database.session import engine

router = APIRouter(tags=["Health"])


class DependencyStatus(BaseModel):
    status:      Literal["ok", "error"]
    latency_ms:  float
    detail:      str | None = None


class ReadinessResponse(BaseModel):
    status:   Literal["ok", "degraded"]
    postgres: DependencyStatus
    redis:    DependencyStatus


@router.get("/health", response_model=dict)
async def liveness() -> dict:
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness() -> JSONResponse:
    """
    Readiness probe — checks that Postgres and Redis are reachable.
    Returns 200 if all healthy, 503 if any dependency is down.
    """
    postgres = await _check_postgres()
    redis    = await _check_redis()

    overall = "ok" if (postgres.status == "ok" and redis.status == "ok") else "degraded"
    body    = ReadinessResponse(status=overall, postgres=postgres, redis=redis)

    status_code = 200 if overall == "ok" else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())


# ------------------------------------------------------------------ #
#  Probe helpers                                                        #
# ------------------------------------------------------------------ #

async def _check_postgres() -> DependencyStatus:
    t0 = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return DependencyStatus(
            status="ok",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
    except Exception as exc:
        return DependencyStatus(
            status="error",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            detail=str(exc),
        )


async def _check_redis() -> DependencyStatus:
    t0 = time.perf_counter()
    try:
        client = await get_redis_client()
        await client.ping()
        return DependencyStatus(
            status="ok",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
    except Exception as exc:
        return DependencyStatus(
            status="error",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            detail=str(exc),
        )
