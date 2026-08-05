"""In-memory inspection result store."""

from __future__ import annotations

from uuid import UUID

from app.plugins.inspection.models import InspectionRecord


class InspectionStore:
    """Shop-scoped store for inspection results (simulation / plugin local)."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, InspectionRecord] = {}
        self._by_shop: dict[UUID, list[UUID]] = {}
        self._by_vehicle: dict[UUID, list[UUID]] = {}

    def save(self, record: InspectionRecord) -> InspectionRecord:
        self._by_id[record.id] = record
        if record.shop_id is not None:
            self._by_shop.setdefault(record.shop_id, [])
            if record.id not in self._by_shop[record.shop_id]:
                self._by_shop[record.shop_id].append(record.id)
        if record.vehicle_id is not None:
            self._by_vehicle.setdefault(record.vehicle_id, [])
            if record.id not in self._by_vehicle[record.vehicle_id]:
                self._by_vehicle[record.vehicle_id].append(record.id)
        return record

    def get(self, inspection_id: UUID) -> InspectionRecord | None:
        return self._by_id.get(inspection_id)

    def list_for_shop(self, shop_id: UUID, *, limit: int = 50) -> list[InspectionRecord]:
        ids = self._by_shop.get(shop_id, [])
        out = [self._by_id[i] for i in reversed(ids) if i in self._by_id]
        return out[:limit]

    def list_for_vehicle(self, vehicle_id: UUID, *, limit: int = 20) -> list[InspectionRecord]:
        ids = self._by_vehicle.get(vehicle_id, [])
        out = [self._by_id[i] for i in reversed(ids) if i in self._by_id]
        return out[:limit]

    def clear(self) -> None:
        self._by_id.clear()
        self._by_shop.clear()
        self._by_vehicle.clear()
