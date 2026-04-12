from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class AuditFilter:
    actor_id:   uuid.UUID | None = None
    target_id:  uuid.UUID | None = None
    event_type: str | None       = None
    from_dt:    datetime | None  = None
    to_dt:      datetime | None  = None


class AbstractAuditRepository(ABC):
    """
    Port (interface) for audit-log persistence.
    Write-only by design — no update or delete operations.
    """

    @abstractmethod
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
        """Persist one audit entry and return its generated ID."""
        ...

    @abstractmethod
    async def list(
        self,
        *,
        filters: AuditFilter | None = None,
        offset:  int = 0,
        limit:   int = 50,
    ) -> tuple[list[Any], int]:
        """Return (rows, total_count) matching filters."""
        ...

    @abstractmethod
    async def get_by_id(self, entry_id: uuid.UUID) -> Any | None: ...
