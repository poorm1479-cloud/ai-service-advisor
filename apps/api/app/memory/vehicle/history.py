"""Vehicle history memory."""

from __future__ import annotations

from uuid import UUID

from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryRecord
from app.memory.service import LongTermMemoryService


class VehicleHistoryService:
    def __init__(self, ltm: LongTermMemoryService) -> None:
        self._ltm = ltm

    async def list_history(
        self, shop_id: UUID, vehicle_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]:
        records = self._ltm.list_memories(shop_id, vehicle_id=vehicle_id, limit=limit * 2)
        preferred = {
            MemoryCategory.VEHICLE_HISTORY.value,
            MemoryCategory.VEHICLE_HEALTH.value,
            MemoryCategory.REPAIR_DECISIONS.value,
        }
        ranked = [
            r
            for r in records
            if r.category.value in preferred or r.memory_type == MemoryType.VEHICLE
        ]
        return (ranked or records)[:limit]
