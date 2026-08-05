"""Calendar service — wraps slot listing on SchedulingStorePort."""

from __future__ import annotations

from uuid import UUID

from app.agents.scheduling.interfaces import SchedulingStorePort
from app.agents.scheduling.models import TimeSlot
from app.agents.scheduling.service import InMemorySchedulingStore


class CalendarPluginService:
    def __init__(self, store: SchedulingStorePort | None = None) -> None:
        self._store = store or InMemorySchedulingStore()

    async def list_slots(self, shop_id: UUID, *, days_ahead: int = 7) -> list[TimeSlot]:
        return await self._store.list_available_slots(shop_id, days_ahead=days_ahead)
