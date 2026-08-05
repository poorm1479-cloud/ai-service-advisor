"""Memory store port + in-memory implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryRecord


class MemoryStorePort(Protocol):
    def save(self, record: MemoryRecord) -> MemoryRecord: ...

    def get(self, shop_id: UUID, memory_id: UUID) -> MemoryRecord | None: ...

    def delete(self, shop_id: UUID, memory_id: UUID) -> bool: ...

    def list(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        memory_type: MemoryType | None = None,
        category: MemoryCategory | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]: ...

    def all_for_shop(self, shop_id: UUID) -> list[MemoryRecord]: ...

    def touch(self, shop_id: UUID, memory_id: UUID) -> None: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._records: dict[UUID, MemoryRecord] = {}

    def save(self, record: MemoryRecord) -> MemoryRecord:
        now = datetime.now(timezone.utc)
        if record.created_at is None:
            record.created_at = now
        record.updated_at = now
        self._records[record.id] = record
        return record

    def get(self, shop_id: UUID, memory_id: UUID) -> MemoryRecord | None:
        rec = self._records.get(memory_id)
        if rec is None or rec.shop_id != shop_id:
            return None
        return rec

    def delete(self, shop_id: UUID, memory_id: UUID) -> bool:
        rec = self.get(shop_id, memory_id)
        if rec is None:
            return False
        del self._records[memory_id]
        return True

    def list(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        memory_type: MemoryType | None = None,
        category: MemoryCategory | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        rows = [r for r in self._records.values() if r.shop_id == shop_id]
        if customer_id is not None:
            rows = [r for r in rows if r.customer_id == customer_id]
        if vehicle_id is not None:
            rows = [r for r in rows if r.vehicle_id == vehicle_id]
        if memory_type is not None:
            rows = [r for r in rows if r.memory_type == memory_type]
        if category is not None:
            rows = [r for r in rows if r.category == category]
        rows.sort(
            key=lambda r: (
                r.importance,
                r.updated_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return rows[:limit]

    def all_for_shop(self, shop_id: UUID) -> list[MemoryRecord]:
        now = datetime.now(timezone.utc)
        out = []
        for r in self._records.values():
            if r.shop_id != shop_id:
                continue
            if r.expires_at and r.expires_at < now:
                continue
            out.append(r)
        return out

    def touch(self, shop_id: UUID, memory_id: UUID) -> None:
        rec = self.get(shop_id, memory_id)
        if rec is None:
            return
        rec.last_accessed_at = datetime.now(timezone.utc)
        rec.access_count += 1
