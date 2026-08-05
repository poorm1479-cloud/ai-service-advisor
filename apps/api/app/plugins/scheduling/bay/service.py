"""Bay assignment — wraps intelligence store when available."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4


class BayPluginService:
    def __init__(self, *, intelligence: Any | None = None, store: Any | None = None) -> None:
        self._intelligence = intelligence
        self._store = store
        self._assignments: dict[UUID, UUID] = {}

    async def list_bays(self, shop_id: UUID) -> list[Any]:
        if self._intelligence is not None and hasattr(self._intelligence, "list_bays"):
            return list(await self._intelligence.list_bays(shop_id))
        resource = getattr(self._store, "_intel", None) or getattr(self._intelligence, "_store", None)
        if resource is not None and hasattr(resource, "list_bays"):
            return list(await resource.list_bays(shop_id))
        return []

    async def assign(
        self, shop_id: UUID, appointment_id: UUID, bay_id: UUID | None = None
    ) -> dict[str, Any]:
        bays = await self.list_bays(shop_id)
        chosen = bay_id
        if chosen is None and bays:
            first = bays[0]
            chosen = getattr(first, "id", None)
        if chosen is None:
            chosen = self._assignments.get(appointment_id) or uuid4()
        self._assignments[appointment_id] = chosen
        return {
            "shop_id": str(shop_id),
            "appointment_id": str(appointment_id),
            "bay_id": str(chosen),
            "assigned": True,
        }
