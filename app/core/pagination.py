"""
Reusable pagination helpers for SQLAlchemy 2.0 async queries.

Two strategies:
  - OffsetPage  — classic page/size (simple, stateless, good for admin UIs)
  - CursorPage  — keyset/cursor (consistent, no drift, good for feeds)

Usage (offset):
    params = OffsetParams(page=2, size=20)
    page   = await paginate(session, select(UserORM).order_by(UserORM.created_at.desc()), params)
    return PaginatedResponse[UserResponse].from_page(page, UserResponse.model_validate)

Usage (cursor):
    params = CursorParams(after="<opaque_cursor>", size=20)
    page   = await cursor_paginate(session, select(UserORM), UserORM.id, params)
"""
from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


# ------------------------------------------------------------------ #
#  Offset pagination                                                   #
# ------------------------------------------------------------------ #

@dataclass
class OffsetParams:
    page: int = 1       # 1-based
    size: int = 20


class OffsetPage(BaseModel, Generic[T]):
    items:       list[T]
    total:       int
    page:        int
    size:        int
    pages:       int
    has_next:    bool
    has_prev:    bool


async def paginate(
    session: AsyncSession,
    stmt: Select,
    params: OffsetParams,
) -> OffsetPage[Any]:
    # Count total without limit/offset
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await session.execute(count_stmt)).scalar_one()

    offset = (params.page - 1) * params.size
    rows   = (await session.execute(stmt.offset(offset).limit(params.size))).scalars().all()

    pages = max(1, math.ceil(total / params.size))
    return OffsetPage(
        items=list(rows),
        total=total,
        page=params.page,
        size=params.size,
        pages=pages,
        has_next=params.page < pages,
        has_prev=params.page > 1,
    )


# ------------------------------------------------------------------ #
#  Cursor pagination (keyset)                                          #
# ------------------------------------------------------------------ #

def _encode_cursor(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(str(value)).encode()).decode()


def _decode_cursor(cursor: str) -> str:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


@dataclass
class CursorParams:
    after:  str | None = None   # opaque base64 cursor
    size:   int        = 20


class CursorPage(BaseModel, Generic[T]):
    items:       list[T]
    next_cursor: str | None
    has_next:    bool


async def cursor_paginate(
    session: AsyncSession,
    stmt: Select,
    cursor_column,          # e.g. UserORM.id or UserORM.created_at
    params: CursorParams,
) -> CursorPage[Any]:
    if params.after:
        decoded = _decode_cursor(params.after)
        stmt    = stmt.where(cursor_column > decoded)

    stmt = stmt.order_by(cursor_column).limit(params.size + 1)
    rows = (await session.execute(stmt)).scalars().all()

    has_next    = len(rows) > params.size
    items       = rows[: params.size]
    next_cursor = _encode_cursor(getattr(items[-1], cursor_column.key)) if has_next else None

    return CursorPage(items=list(items), next_cursor=next_cursor, has_next=has_next)


# ------------------------------------------------------------------ #
#  FastAPI query-param dependency                                      #
# ------------------------------------------------------------------ #

def offset_params(
    page: int = Query(default=1,  ge=1,   description="Page number (1-based)"),
    size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> OffsetParams:
    return OffsetParams(page=page, size=size)
