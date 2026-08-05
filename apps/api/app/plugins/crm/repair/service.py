"""Repair plugin service — wraps vehicle directory repair APIs (no rewrite)."""

from __future__ import annotations

from uuid import UUID

from app.agents.vehicle.interfaces import VehicleDirectoryPort
from app.agents.vehicle.models import RepairRecord
from app.agents.vehicle.service import InMemoryVehicleDirectory


class RepairPluginService:
    """Thin wrapper around existing repair history on the vehicle directory."""

    def __init__(self, directory: VehicleDirectoryPort | None = None) -> None:
        self._directory = directory or InMemoryVehicleDirectory()

    @property
    def directory(self) -> VehicleDirectoryPort:
        return self._directory

    async def list_by_vehicle(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairRecord]:
        return await self._directory.list_repairs(shop_id, vehicle_id)

    async def add(self, shop_id: UUID, repair: RepairRecord) -> RepairRecord:
        if hasattr(self._directory, "add_repair"):
            return await self._directory.add_repair(shop_id, repair)  # type: ignore[no-any-return]
        raise RuntimeError("Underlying vehicle directory does not support add_repair")
