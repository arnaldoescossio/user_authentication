from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# ContextVar so the request-id is accessible from any log call within a request
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_ctx.get()


# ------------------------------------------------------------------ #
#  JSON log formatter                                                  #
# ------------------------------------------------------------------ #

import json


class JSONFormatter(logging.Formatter):
    """
    Emit every log record as a single-line JSON object.
    Compatible with log aggregators (Datadog, Loki, CloudWatch).
    """

    LEVEL_MAP = {
        logging.DEBUG:    "debug",
        logging.INFO:     "info",
        logging.WARNING:  "warning",
        logging.ERROR:    "error",
        logging.CRITICAL: "critical",
    }

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":     self.LEVEL_MAP.get(record.levelno, record.levelname.lower()),
            "logger":    record.name,
            "message":   record.getMessage(),
            "request_id": get_request_id() or None,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge any extra fields passed via logger.info("…", extra={…})
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                payload[key] = value

        return json.dumps(payload, default=str)


# ------------------------------------------------------------------ #
#  Setup                                                               #
# ------------------------------------------------------------------ #

def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ------------------------------------------------------------------ #
#  Request-logging middleware                                          #
# ------------------------------------------------------------------ #

logger = logging.getLogger("app.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique request-id to every request and logs:
      - Incoming request (method + path + client IP)
      - Outgoing response (status code + latency ms)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        token      = _request_id_ctx.set(request_id)

        start = time.perf_counter()

        # Add request-id to response headers so clients can correlate
        try:
            response = await call_next(request)
        except Exception:
            _request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            f"{request.method} {request.url.path} → {response.status_code}",
            extra={
                "http_method":  request.method,
                "http_path":    request.url.path,
                "http_status":  response.status_code,
                "duration_ms":  duration_ms,
                "client_ip":    request.client.host if request.client else None,
            },
        )

        response.headers["X-Request-ID"] = request_id
        _request_id_ctx.reset(token)
        return response
