"""Customer history memory."""

from __future__ import annotations

from uuid import UUID

from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryRecord
from app.memory.service import LongTermMemoryService


class CustomerHistoryService:
    def __init__(self, ltm: LongTermMemoryService) -> None:
        self._ltm = ltm

    async def list_history(
        self, shop_id: UUID, customer_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]:
        records = self._ltm.list_memories(shop_id, customer_id=customer_id, limit=limit * 2)
        # Prefer history / conversation / preference categories
        preferred = {
            MemoryCategory.CUSTOMER_HISTORY.value,
            MemoryCategory.CUSTOMER_PREFERENCES.value,
            MemoryCategory.PREVIOUS_CONVERSATIONS.value,
            MemoryCategory.REPAIR_DECISIONS.value,
            MemoryCategory.DECLINED_ESTIMATES.value,
            MemoryCategory.APPOINTMENT_BEHAVIOR.value,
        }
        ranked = [
            r
            for r in records
            if r.category.value in preferred or r.memory_type == MemoryType.CUSTOMER
        ]
        if not ranked:
            ranked = records
        return ranked[:limit]
