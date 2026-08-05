"""Communication plugin service — wraps existing CrmStorePort (no rewrite)."""

from __future__ import annotations

from uuid import UUID

from app.agents.crm.interfaces import CrmStorePort
from app.agents.crm.models import TimelineEntry
from app.agents.crm.service import InMemoryCrmStore


class CommunicationPluginService:
    """Thin wrapper around existing CRM store (timeline / communications)."""

    def __init__(self, store: CrmStorePort | None = None) -> None:
        self._store = store or InMemoryCrmStore()

    @property
    def store(self) -> CrmStorePort:
        return self._store

    async def add_communication(
        self,
        shop_id: UUID,
        customer_id: UUID,
        channel: str,
        message: str,
        direction: str = "incoming",
    ) -> TimelineEntry:
        return await self._store.add_communication(
            shop_id, customer_id, channel, message, direction=direction
        )

    async def add_repair_note(
        self, shop_id: UUID, customer_id: UUID, vehicle_id: UUID | None, note: str
    ) -> TimelineEntry:
        return await self._store.add_repair_note(shop_id, customer_id, vehicle_id, note)

    async def add_timeline(
        self, shop_id: UUID, customer_id: UUID, kind: str, summary: str
    ) -> TimelineEntry:
        return await self._store.add_timeline(shop_id, customer_id, kind, summary)

    async def list_timeline(self, shop_id: UUID, customer_id: UUID) -> list[TimelineEntry]:
        return await self._store.list_timeline(shop_id, customer_id)

    async def list_communications(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[TimelineEntry]:
        timeline = await self._store.list_timeline(shop_id, customer_id)
        return [e for e in timeline if e.kind == "communication"]
