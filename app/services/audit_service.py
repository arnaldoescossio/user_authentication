"""
AuditLogService — fire-and-forget, write-only audit trail.

Now delegates persistence to AbstractAuditRepository (proper Ports & Adapters).
Falls back to a direct session if no repo is injected (background writes).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.infrastructure.database.audit_models import AuditEvent
from app.infrastructure.database.audit_repository import SQLAuditRepository
from app.infrastructure.database.session import AsyncSessionLocal

log = logging.getLogger("app.audit")


class AuditLogService:

    def __init__(self, repo: SQLAuditRepository | None = None) -> None:
        self._repo = repo  # injected for in-request writes; None = use own session

    async def record(
        self,
        event_type: AuditEvent | str,
        *,
        actor_id:   uuid.UUID | None = None,
        target_id:  uuid.UUID | None = None,
        ip_address: str | None       = None,
        user_agent: str | None       = None,
        metadata:   dict[str, Any] | None = None,
    ) -> None:
        """Write via injected repo (request context) — raises on failure."""
        if self._repo is None:
            await self.log(event_type, actor_id=actor_id, target_id=target_id,
                           ip_address=ip_address, user_agent=user_agent, metadata=metadata)
            return
        await self._repo.append(
            event_type=str(event_type),
            actor_id=actor_id,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    #  Static fire-and-forget (background, own session, never raises)     #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def log(
        event_type: AuditEvent | str,
        *,
        actor_id:   uuid.UUID | None = None,
        target_id:  uuid.UUID | None = None,
        ip_address: str | None       = None,
        user_agent: str | None       = None,
        metadata:   dict[str, Any] | None = None,
    ) -> None:
        """Background write — opens its own session, never raises."""
        try:
            async with AsyncSessionLocal() as session:
                repo = SQLAuditRepository(session)
                await repo.append(
                    event_type=str(event_type),
                    actor_id=actor_id,
                    target_id=target_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    metadata=metadata,
                )
                await session.commit()
        except Exception as exc:
            log.error("Audit log write failed",
                      extra={"event_type": str(event_type), "error": str(exc)})

    # ------------------------------------------------------------------ #
    #  Typed convenience wrappers                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def user_registered(user_id: uuid.UUID, *, ip: str | None = None) -> None:
        await AuditLogService.log(AuditEvent.USER_REGISTERED,
                                  actor_id=user_id, target_id=user_id, ip_address=ip)

    @staticmethod
    async def login_success(user_id: uuid.UUID, *, ip: str | None = None,
                            ua: str | None = None) -> None:
        await AuditLogService.log(AuditEvent.USER_LOGIN_SUCCESS,
                                  actor_id=user_id, ip_address=ip, user_agent=ua)

    @staticmethod
    async def login_failed(email: str, *, ip: str | None = None) -> None:
        await AuditLogService.log(AuditEvent.USER_LOGIN_FAILED,
                                  ip_address=ip, metadata={"email": email})

    @staticmethod
    async def logout(user_id: uuid.UUID, *, ip: str | None = None) -> None:
        await AuditLogService.log(AuditEvent.USER_LOGOUT,
                                  actor_id=user_id, ip_address=ip)

    @staticmethod
    async def password_changed(user_id: uuid.UUID, *, ip: str | None = None) -> None:
        await AuditLogService.log(AuditEvent.PASSWORD_CHANGED,
                                  actor_id=user_id, target_id=user_id, ip_address=ip)

    @staticmethod
    async def role_changed(admin_id: uuid.UUID, target_id: uuid.UUID,
                           *, old_role: str, new_role: str) -> None:
        await AuditLogService.log(AuditEvent.USER_ROLE_CHANGED,
                                  actor_id=admin_id, target_id=target_id,
                                  metadata={"old_role": old_role, "new_role": new_role})

    @staticmethod
    async def status_changed(admin_id: uuid.UUID, target_id: uuid.UUID,
                             *, old_status: str, new_status: str) -> None:
        await AuditLogService.log(AuditEvent.USER_STATUS_CHANGED,
                                  actor_id=admin_id, target_id=target_id,
                                  metadata={"old_status": old_status, "new_status": new_status})

    @staticmethod
    async def user_deleted(admin_id: uuid.UUID, target_id: uuid.UUID) -> None:
        await AuditLogService.log(AuditEvent.USER_DELETED,
                                  actor_id=admin_id, target_id=target_id)
