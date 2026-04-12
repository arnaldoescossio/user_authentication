"""
Audit log — immutable append-only record of every security-relevant action.

Every event stores:
  - who  (actor_id — the user performing the action, nullable for anonymous)
  - what (event_type enum)
  - target (target_id — the resource affected, nullable)
  - context (IP address, user-agent, extra JSON payload)
  - when (created_at — server-side, timezone-aware)

The table is intentionally write-only from the application perspective:
no UPDATE or DELETE is ever issued against it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models import Base


class AuditEvent(StrEnum):
    # Auth
    USER_REGISTERED      = "user.registered"
    USER_LOGIN_SUCCESS   = "user.login_success"
    USER_LOGIN_FAILED    = "user.login_failed"
    USER_LOGOUT          = "user.logout"
    TOKEN_REFRESHED      = "token.refreshed"

    # Account
    PASSWORD_CHANGED     = "account.password_changed"
    PASSWORD_RESET_REQ   = "account.password_reset_requested"
    PASSWORD_RESET_DONE  = "account.password_reset_completed"
    EMAIL_VERIFY_REQ     = "account.email_verify_requested"
    EMAIL_VERIFIED       = "account.email_verified"

    # Admin
    USER_ROLE_CHANGED    = "admin.user_role_changed"
    USER_STATUS_CHANGED  = "admin.user_status_changed"
    USER_DELETED         = "admin.user_deleted"


class AuditLogORM(Base):
    """
    Immutable audit log entry.
    Never updated or deleted — only inserted.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text,       nullable=True)
    metadata_:  Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.event_type} actor={self.actor_id} @ {self.created_at}>"
