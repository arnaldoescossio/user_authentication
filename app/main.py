from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AuthException
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.rate_limit import SlidingWindowRateLimitMiddleware
from app.infrastructure.cache.token_cache import get_redis_client
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import engine

import logging

log = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    configure_logging(level="DEBUG" if settings.debug else "INFO")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await get_redis_client()
    log.info("Application started", extra={"env": settings.app_env})

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await engine.dispose()
    log.info("Application stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Production-grade Auth & Authorization API with JWT + Redis token cache.",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ──────────────────────
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SlidingWindowRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ───────────────────────────────────────────────
    @app.exception_handler(AuthException)
    async def auth_exception_handler(_: Request, exc: AuthException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or {},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("app.error").exception("Unhandled exception", exc_info=exc)
        if settings.debug:
            raise exc
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred."},
        )

    # ── Routers ──────────────────────────────────────────────────────────
    app.include_router(api_router)

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
