from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.audit_repository import AbstractAuditRepository, AuditFilter
from app.infrastructure.database.audit_models import AuditLogORM


class SQLAuditRepository(AbstractAuditRepository):
    """
    SQLAlchemy 2.0 async implementation of AbstractAuditRepository.
    Append-only: no update or delete methods are provided.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    async def append(
        self,
        *,
        event_type:  str,
        actor_id:    uuid.UUID | None = None,
        target_id:   uuid.UUID | None = None,
        ip_address:  str | None       = None,
        user_agent:  str | None       = None,
        metadata:    dict[str, Any] | None = None,
    ) -> uuid.UUID:
        entry = AuditLogORM(
            id=uuid.uuid4(),
            actor_id=actor_id,
            event_type=event_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_=metadata,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry.id

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    async def list(
        self,
        *,
        filters: AuditFilter | None = None,
        offset:  int = 0,
        limit:   int = 50,
    ) -> tuple[list[AuditLogORM], int]:
        stmt = select(AuditLogORM).order_by(AuditLogORM.created_at.desc())

        if filters:
            if filters.actor_id:
                stmt = stmt.where(AuditLogORM.actor_id == filters.actor_id)
            if filters.target_id:
                stmt = stmt.where(AuditLogORM.target_id == filters.target_id)
            if filters.event_type:
                stmt = stmt.where(AuditLogORM.event_type == filters.event_type)
            if filters.from_dt:
                stmt = stmt.where(AuditLogORM.created_at >= filters.from_dt)
            if filters.to_dt:
                stmt = stmt.where(AuditLogORM.created_at <= filters.to_dt)

        # Total count (reuse filtered stmt as subquery)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        rows = (await self._session.execute(stmt.offset(offset).limit(limit))).scalars().all()
        return list(rows), total

    async def get_by_id(self, entry_id: uuid.UUID) -> AuditLogORM | None:
        stmt   = select(AuditLogORM).where(AuditLogORM.id == entry_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
