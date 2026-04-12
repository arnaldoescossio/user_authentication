from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import CredentialsException, TokenExpiredException


class TokenType:
    ACCESS = "access"
    REFRESH = "refresh"


class JWTService:
    """
    Handles creation and verification of JWT access and refresh tokens.

    Payload fields:
        sub  – subject (user_id as str)
        jti  – unique token id (for revocation)
        type – "access" | "refresh"
        role – user role string
        exp  – expiry (set by jose automatically)
        iat  – issued-at
    """

    def __init__(self) -> None:
        self._secret = settings.secret_key
        self._algorithm = settings.jwt_algorithm
        self._access_ttl = timedelta(minutes=settings.access_token_expire_minutes)
        self._refresh_ttl = timedelta(days=settings.refresh_token_expire_days)

    # ------------------------------------------------------------------ #
    #  Creation                                                            #
    # ------------------------------------------------------------------ #

    def create_access_token(self, user_id: str, role: str) -> tuple[str, str]:
        """Return (encoded_token, jti)."""
        jti = str(uuid.uuid4())
        payload = self._build_payload(
            subject=user_id,
            jti=jti,
            token_type=TokenType.ACCESS,
            role=role,
            ttl=self._access_ttl,
        )
        return jwt.encode(payload, self._secret, algorithm=self._algorithm), jti

    def create_refresh_token(self, user_id: str) -> tuple[str, str]:
        """Return (encoded_token, jti)."""
        jti = str(uuid.uuid4())
        payload = self._build_payload(
            subject=user_id,
            jti=jti,
            token_type=TokenType.REFRESH,
            role=None,
            ttl=self._refresh_ttl,
        )
        return jwt.encode(payload, self._secret, algorithm=self._algorithm), jti

    # ------------------------------------------------------------------ #
    #  Verification                                                        #
    # ------------------------------------------------------------------ #

    def decode_access_token(self, token: str) -> dict[str, Any]:
        return self._decode(token, expected_type=TokenType.ACCESS)

    def decode_refresh_token(self, token: str) -> dict[str, Any]:
        return self._decode(token, expected_type=TokenType.REFRESH)

    # ------------------------------------------------------------------ #
    #  TTL helpers (for Redis)                                             #
    # ------------------------------------------------------------------ #

    @property
    def access_token_ttl_seconds(self) -> int:
        return int(self._access_ttl.total_seconds())

    @property
    def refresh_token_ttl_seconds(self) -> int:
        return int(self._refresh_ttl.total_seconds())

    # ------------------------------------------------------------------ #
    #  Private                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_payload(
        *,
        subject: str,
        jti: str,
        token_type: str,
        role: str | None,
        ttl: timedelta,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": subject,
            "jti": jti,
            "type": token_type,
            "iat": now,
            "exp": now + ttl,
        }
        if role is not None:
            payload["role"] = role
        return payload

    def _decode(self, token: str, expected_type: str) -> dict[str, Any]:
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException()
        except JWTError:
            raise CredentialsException()

        if payload.get("type") != expected_type:
            raise CredentialsException("Invalid token type.")

        if not payload.get("sub") or not payload.get("jti"):
            raise CredentialsException("Token is missing required claims.")

        return payload


# Module-level singleton
jwt_service = JWTService()
