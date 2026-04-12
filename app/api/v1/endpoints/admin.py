"""
Admin-only endpoints:
  GET  /api/v1/admin/users          — paginated, filterable user list
  GET  /api/v1/admin/users/{id}/audit — audit trail for a specific user
  GET  /api/v1/admin/audit           — global audit log (paginated)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import UserResponse
from app.core.dependencies import AdminUser, get_user_repository
from app.core.pagination import OffsetPage, OffsetParams, offset_params, paginate
from app.domain.entities.user import UserRole, UserStatus
from app.infrastructure.database.audit_models import AuditLogORM
from app.infrastructure.database.models import UserORM
from app.infrastructure.database.session import get_db
from app.infrastructure.database.user_repository import SQLUserRepository
from app.services.audit_service import AuditLogService

router = APIRouter(prefix="/admin", tags=["Admin"])


# ------------------------------------------------------------------ #
#  Schemas                                                             #
# ------------------------------------------------------------------ #

class AuditLogResponse(BaseModel):
    id:         uuid.UUID
    actor_id:   uuid.UUID | None
    event_type: str
    target_id:  uuid.UUID | None
    ip_address: str | None
    user_agent: str | None
    metadata:   dict | None
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, row: AuditLogORM) -> "AuditLogResponse":
        return cls(
            id=row.id,
            actor_id=row.actor_id,
            event_type=row.event_type,
            target_id=row.target_id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            metadata=row.metadata_,
            created_at=row.created_at.isoformat(),
        )


# ------------------------------------------------------------------ #
#  User list                                                           #
# ------------------------------------------------------------------ #

@router.get("/users", response_model=OffsetPage[UserResponse])
async def list_users(
    _admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[OffsetParams, Depends(offset_params)],
    role:   UserRole | None = Query(default=None, description="Filter by role"),
    status: UserStatus | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search email or username"),
) -> OffsetPage[UserResponse]:
    """[Admin] Paginated, filterable list of all users."""
    stmt = select(UserORM).order_by(UserORM.created_at.desc())

    if role:
        stmt = stmt.where(UserORM.role == role)
    if status:
        stmt = stmt.where(UserORM.status == status)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            UserORM.email.ilike(pattern) | UserORM.username.ilike(pattern)
        )

    raw_page = await paginate(session, stmt, params)

    return OffsetPage[UserResponse](
        items=[
            UserResponse.model_validate(orm, from_attributes=True)
            for orm in raw_page.items
        ],
        total=raw_page.total,
        page=raw_page.page,
        size=raw_page.size,
        pages=raw_page.pages,
        has_next=raw_page.has_next,
        has_prev=raw_page.has_prev,
    )


# ------------------------------------------------------------------ #
#  Audit log — per-user                                               #
# ------------------------------------------------------------------ #

@router.get("/users/{user_id}/audit", response_model=OffsetPage[AuditLogResponse])
async def user_audit_log(
    user_id: uuid.UUID,
    _admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[OffsetParams, Depends(offset_params)],
) -> OffsetPage[AuditLogResponse]:
    """[Admin] Audit trail for a specific user (as actor or target)."""
    stmt = (
        select(AuditLogORM)
        .where(
            (AuditLogORM.actor_id == user_id) | (AuditLogORM.target_id == user_id)
        )
        .order_by(AuditLogORM.created_at.desc())
    )

    raw_page = await paginate(session, stmt, params)
    return OffsetPage[AuditLogResponse](
        items=[AuditLogResponse.from_orm(r) for r in raw_page.items],
        total=raw_page.total,
        page=raw_page.page,
        size=raw_page.size,
        pages=raw_page.pages,
        has_next=raw_page.has_next,
        has_prev=raw_page.has_prev,
    )


# ------------------------------------------------------------------ #
#  Audit log — global                                                  #
# ------------------------------------------------------------------ #

@router.get("/audit", response_model=OffsetPage[AuditLogResponse])
async def global_audit_log(
    _admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[OffsetParams, Depends(offset_params)],
    event_type: str | None = Query(default=None, description="Filter by event type"),
) -> OffsetPage[AuditLogResponse]:
    """[Admin] Global audit log — most recent first."""
    stmt = select(AuditLogORM).order_by(AuditLogORM.created_at.desc())

    if event_type:
        stmt = stmt.where(AuditLogORM.event_type == event_type)

    raw_page = await paginate(session, stmt, params)
    return OffsetPage[AuditLogResponse](
        items=[AuditLogResponse.from_orm(r) for r in raw_page.items],
        total=raw_page.total,
        page=raw_page.page,
        size=raw_page.size,
        pages=raw_page.pages,
        has_next=raw_page.has_next,
        has_prev=raw_page.has_prev,
    )
