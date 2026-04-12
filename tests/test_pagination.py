"""
Unit tests for the pagination helpers (offset + cursor).
Uses an in-memory SQLite engine — no Postgres needed.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.pagination import (
    CursorParams,
    OffsetParams,
    cursor_paginate,
    paginate,
)


# ------------------------------------------------------------------ #
#  Minimal test model                                                  #
# ------------------------------------------------------------------ #

class _Base(DeclarativeBase):
    pass


class _Item(_Base):
    __tablename__ = "test_items"
    id:    Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    label: Mapped[str]       = mapped_column(String(50))


_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True, scope="module")
async def _setup():
    async with _engine.begin() as c:
        await c.run_sync(_Base.metadata.create_all)
    async with _Session() as s:
        for i in range(15):
            s.add(_Item(label=f"item-{i:02d}"))
        await s.commit()
    yield
    async with _engine.begin() as c:
        await c.run_sync(_Base.metadata.drop_all)


# ------------------------------------------------------------------ #
#  Offset pagination                                                   #
# ------------------------------------------------------------------ #

class TestOffsetPagination:
    @pytest.mark.asyncio
    async def test_first_page(self):
        from sqlalchemy import select
        async with _Session() as s:
            page = await paginate(s, select(_Item).order_by(_Item.label), OffsetParams(page=1, size=5))
        assert len(page.items) == 5
        assert page.total == 15
        assert page.pages == 3
        assert page.has_next is True
        assert page.has_prev is False

    @pytest.mark.asyncio
    async def test_last_page(self):
        from sqlalchemy import select
        async with _Session() as s:
            page = await paginate(s, select(_Item).order_by(_Item.label), OffsetParams(page=3, size=5))
        assert len(page.items) == 5
        assert page.has_next is False
        assert page.has_prev is True

    @pytest.mark.asyncio
    async def test_partial_last_page(self):
        from sqlalchemy import select
        async with _Session() as s:
            page = await paginate(s, select(_Item).order_by(_Item.label), OffsetParams(page=2, size=8))
        assert len(page.items) == 7      # 15 - 8 = 7 on second page
        assert page.total == 15
        assert page.has_next is False

    @pytest.mark.asyncio
    async def test_single_page(self):
        from sqlalchemy import select
        async with _Session() as s:
            page = await paginate(s, select(_Item).order_by(_Item.label), OffsetParams(page=1, size=20))
        assert len(page.items) == 15
        assert page.pages == 1
        assert page.has_next is False
        assert page.has_prev is False


# ------------------------------------------------------------------ #
#  Cursor pagination                                                   #
# ------------------------------------------------------------------ #

class TestCursorPagination:
    @pytest.mark.asyncio
    async def test_first_page_no_cursor(self):
        from sqlalchemy import select
        async with _Session() as s:
            page = await cursor_paginate(
                s, select(_Item).order_by(_Item.label), _Item.label,
                CursorParams(after=None, size=5),
            )
        assert len(page.items) == 5
        assert page.has_next is True
        assert page.next_cursor is not None

    @pytest.mark.asyncio
    async def test_second_page_via_cursor(self):
        from sqlalchemy import select
        async with _Session() as s:
            p1 = await cursor_paginate(
                s, select(_Item).order_by(_Item.label), _Item.label,
                CursorParams(after=None, size=5),
            )
            p2 = await cursor_paginate(
                s, select(_Item).order_by(_Item.label), _Item.label,
                CursorParams(after=p1.next_cursor, size=5),
            )
        assert len(p2.items) == 5
        # Pages must not overlap
        p1_labels = {i.label for i in p1.items}
        p2_labels = {i.label for i in p2.items}
        assert p1_labels.isdisjoint(p2_labels)

    @pytest.mark.asyncio
    async def test_last_page_has_no_next_cursor(self):
        from sqlalchemy import select
        async with _Session() as s:
            p1 = await cursor_paginate(
                s, select(_Item).order_by(_Item.label), _Item.label,
                CursorParams(after=None, size=10),
            )
            p2 = await cursor_paginate(
                s, select(_Item).order_by(_Item.label), _Item.label,
                CursorParams(after=p1.next_cursor, size=10),
            )
        assert p2.has_next is False
        assert p2.next_cursor is None
