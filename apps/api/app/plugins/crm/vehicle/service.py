"""Vehicle plugin service — wraps existing VehicleDirectoryPort (no rewrite)."""

from __future__ import annotations

from uuid import UUID

from app.agents.vehicle.interfaces import VehicleDirectoryPort
from app.agents.vehicle.models import VehicleRecord
from app.agents.vehicle.service import InMemoryVehicleDirectory


class VehiclePluginService:
    """Thin wrapper around existing vehicle directory implementation."""

    def __init__(self, directory: VehicleDirectoryPort | None = None) -> None:
        self._directory = directory or InMemoryVehicleDirectory()

    @property
    def directory(self) -> VehicleDirectoryPort:
        return self._directory

    async def find_by_id(self, shop_id: UUID, vehicle_id: UUID) -> VehicleRecord | None:
        return await self._directory.find_by_id(shop_id, vehicle_id)

    async def find_by_vin(self, shop_id: UUID, vin: str) -> VehicleRecord | None:
        return await self._directory.find_by_vin(shop_id, vin)

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[VehicleRecord]:
        return await self._directory.list_by_customer(shop_id, customer_id)

    async def search(self, shop_id: UUID, query: str) -> list[VehicleRecord]:
        q = query.strip().upper()
        # Directory has no global search — scan via VIN match / partial
        found = await self._directory.find_by_vin(shop_id, q) if len(q) >= 8 else None
        if found:
            return [found]
        # Best-effort: empty when no VIN match (existing behavior preserved)
        return []

    async def create(self, vehicle: VehicleRecord) -> VehicleRecord:
        return await self._directory.create(vehicle)

    async def update(self, vehicle: VehicleRecord) -> VehicleRecord:
        return await self._directory.update(vehicle)
