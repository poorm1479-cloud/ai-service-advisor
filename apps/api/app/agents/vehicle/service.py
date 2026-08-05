"""Vehicle Agent — pure Decision Layer (resolve / recommend create-mileage)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.errors import AgentValidationError
from app.agents.decisions.types import VehicleDecision
from app.agents.vehicle.interfaces import VehicleDirectoryPort
from app.agents.vehicle.models import (
    MaintenanceItem,
    RepairRecord,
    VehicleRecord,
    VehicleResolveRequest,
    VehicleResolveResult,
)

_MAINTENANCE_INTERVALS = [
    ("oil_change", 5000),
    ("tire_rotation", 7500),
    ("cabin_filter", 15000),
    ("brake_inspection", 20000),
    ("transmission_service", 60000),
]


class InMemoryVehicleDirectory:
    def __init__(self) -> None:
        self._vehicles: dict[UUID, VehicleRecord] = {}
        self._repairs: dict[UUID, list[RepairRecord]] = {}

    async def find_by_id(self, shop_id: UUID, vehicle_id: UUID) -> VehicleRecord | None:
        v = self._vehicles.get(vehicle_id)
        return v if v and v.shop_id == shop_id else None

    async def find_by_vin(self, shop_id: UUID, vin: str) -> VehicleRecord | None:
        vin_u = vin.upper()
        for v in self._vehicles.values():
            if v.shop_id == shop_id and v.vin == vin_u:
                return v
        return None

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[VehicleRecord]:
        return [
            v
            for v in self._vehicles.values()
            if v.shop_id == shop_id and v.customer_id == customer_id
        ]

    async def create(self, vehicle: VehicleRecord) -> VehicleRecord:
        self._vehicles[vehicle.id] = vehicle
        self._repairs.setdefault(vehicle.id, [])
        return vehicle

    async def update(self, vehicle: VehicleRecord) -> VehicleRecord:
        self._vehicles[vehicle.id] = vehicle
        return vehicle

    async def list_repairs(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairRecord]:
        vehicle = await self.find_by_id(shop_id, vehicle_id)
        if vehicle is None:
            return []
        return list(self._repairs.get(vehicle_id, []))

    async def add_repair(self, shop_id: UUID, repair: RepairRecord) -> RepairRecord:
        if await self.find_by_id(shop_id, repair.vehicle_id) is None:
            raise AgentValidationError("Vehicle not found", agent="vehicle")
        self._repairs.setdefault(repair.vehicle_id, []).append(repair)
        return repair


class VehicleAgent(Agent[VehicleResolveRequest, VehicleResolveResult]):
    name = "vehicle"

    def __init__(self, directory: VehicleDirectoryPort | None = None) -> None:
        super().__init__()
        self._directory = directory or InMemoryVehicleDirectory()

    @property
    def directory(self) -> VehicleDirectoryPort:
        return self._directory

    async def handle(
        self, payload: VehicleResolveRequest, context: AgentContext
    ) -> AgentResult[VehicleResolveResult]:
        return await self.resolve(payload, context)

    async def resolve(
        self, request: VehicleResolveRequest, context: AgentContext
    ) -> AgentResult[VehicleResolveResult]:
        shop_id = context.shop_id
        vehicle: VehicleRecord | None = None
        action = "none"
        decision: VehicleDecision | None = None

        if request.vin:
            vehicle = await self._directory.find_by_vin(shop_id, request.vin.upper())
            if vehicle:
                action = "found_by_vin"

        if vehicle is None and (request.customer_id or context.customer_id):
            cid = request.customer_id or context.customer_id
            assert cid is not None
            vehicles = await self._directory.list_by_customer(shop_id, cid)
            if vehicles:
                vehicle = vehicles[0]
                action = "found_by_customer"

        if vehicle is None and request.create_if_missing:
            if not request.vin or not request.year or not request.make or not request.model:
                raise AgentValidationError(
                    "VIN, year, make, and model required to create vehicle",
                    agent=self.name,
                    correlation_id=context.correlation_id,
                )
            decision = VehicleDecision(
                action="create",
                vin=request.vin,
                year=request.year,
                make=request.make,
                model=request.model,
                mileage=request.mileage or 0,
                customer_id=request.customer_id or context.customer_id,
                rationale="No match — recommend create vehicle",
            )
            provisional = VehicleRecord(
                id=uuid4(),
                shop_id=shop_id,
                vin=request.vin.upper(),
                year=request.year,
                make=request.make,
                model=request.model,
                mileage=request.mileage or 0,
                customer_id=request.customer_id or context.customer_id,
            )
            timeline = self.generate_maintenance_timeline(provisional, [])
            return AgentResult.ok(
                VehicleResolveResult(
                    vehicle=provisional,
                    repair_history=[],
                    maintenance_timeline=timeline,
                    action="propose_create",
                    decision=decision,
                )
            )

        if vehicle is None:
            return AgentResult.ok(VehicleResolveResult(vehicle=None, action="not_found"))

        if request.mileage is not None and request.mileage > vehicle.mileage:
            decision = VehicleDecision(
                action="update_mileage",
                vehicle_id=vehicle.id,
                mileage=request.mileage,
                customer_id=vehicle.customer_id,
                rationale="Recommend mileage update",
            )
            # Preview updated mileage for AI without persisting
            vehicle = VehicleRecord(
                id=vehicle.id,
                shop_id=vehicle.shop_id,
                vin=vehicle.vin,
                year=vehicle.year,
                make=vehicle.make,
                model=vehicle.model,
                mileage=request.mileage,
                customer_id=vehicle.customer_id,
                license_plate=vehicle.license_plate,
            )
            action = "propose_mileage_update" if action == "none" else f"{action}+propose_mileage"

        repairs = await self._directory.list_repairs(shop_id, vehicle.id) if action != "propose_create" else []
        # For found vehicles, load real repairs
        if "propose_create" not in action and vehicle.id:
            try:
                repairs = await self._directory.list_repairs(shop_id, vehicle.id)
            except Exception:  # noqa: BLE001
                repairs = []
        timeline = self.generate_maintenance_timeline(vehicle, repairs)
        if decision is None:
            context.vehicle_id = vehicle.id
            context.customer_id = vehicle.customer_id or context.customer_id

        return AgentResult.ok(
            VehicleResolveResult(
                vehicle=vehicle,
                repair_history=repairs,
                maintenance_timeline=timeline,
                action=action,
                decision=decision,
            )
        )

    async def update_mileage(
        self, vehicle_id: UUID, mileage: int, context: AgentContext
    ) -> VehicleRecord:
        """Propose mileage update — returns preview; Workflow persists."""
        if mileage < 0:
            raise AgentValidationError("Mileage cannot be negative", agent=self.name)
        vehicle = await self._directory.find_by_id(context.shop_id, vehicle_id)
        if vehicle is None:
            raise AgentValidationError("Vehicle not found", agent=self.name)
        if mileage < vehicle.mileage:
            raise AgentValidationError(
                "New mileage cannot be less than current mileage",
                agent=self.name,
            )
        return VehicleRecord(
            id=vehicle.id,
            shop_id=vehicle.shop_id,
            vin=vehicle.vin,
            year=vehicle.year,
            make=vehicle.make,
            model=vehicle.model,
            mileage=mileage,
            customer_id=vehicle.customer_id,
            license_plate=vehicle.license_plate,
        )

    def generate_maintenance_timeline(
        self, vehicle: VehicleRecord, repairs: list[RepairRecord]
    ) -> list[MaintenanceItem]:
        performed = {r.service_type.lower().replace(" ", "_") for r in repairs}
        items: list[MaintenanceItem] = []
        now = datetime.now(timezone.utc)
        for service, interval in _MAINTENANCE_INTERVALS:
            due = ((vehicle.mileage // interval) + 1) * interval
            status = (
                "completed"
                if service in performed
                else "due_soon"
                if due - vehicle.mileage <= 1000
                else "scheduled"
            )
            items.append(
                MaintenanceItem(
                    service=service,
                    due_mileage=due,
                    due_date=now,
                    status=status,
                    notes=f"Every {interval} miles",
                )
            )
        return items

    async def read_repair_history(
        self, vehicle_id: UUID, context: AgentContext
    ) -> AgentResult[list[RepairRecord]]:
        repairs = await self._directory.list_repairs(context.shop_id, vehicle_id)
        return AgentResult.ok(repairs)
