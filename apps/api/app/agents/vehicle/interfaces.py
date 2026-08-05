"""Vehicle agent ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.vehicle.models import (
    RepairRecord,
    VehicleRecord,
    VehicleResolveRequest,
    VehicleResolveResult,
)


class VehicleDirectoryPort(Protocol):
    async def find_by_id(self, shop_id: UUID, vehicle_id: UUID) -> VehicleRecord | None: ...

    async def find_by_vin(self, shop_id: UUID, vin: str) -> VehicleRecord | None: ...

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[VehicleRecord]: ...

    async def create(self, vehicle: VehicleRecord) -> VehicleRecord: ...

    async def update(self, vehicle: VehicleRecord) -> VehicleRecord: ...

    async def list_repairs(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairRecord]: ...


class VehicleAgentPort(Protocol):
    async def resolve(
        self, request: VehicleResolveRequest, context: AgentContext
    ) -> AgentResult[VehicleResolveResult]: ...
