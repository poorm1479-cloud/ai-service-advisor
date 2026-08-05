"""Vehicle agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class VehicleRecord:
    id: UUID
    shop_id: UUID
    vin: str
    year: int
    make: str
    model: str
    mileage: int
    customer_id: UUID | None = None
    license_plate: str | None = None


@dataclass(slots=True)
class RepairRecord:
    id: UUID
    vehicle_id: UUID
    service_type: str
    description: str
    cost: float
    performed_at: datetime | None = None
    recommendation: str | None = None


@dataclass(slots=True)
class MaintenanceItem:
    service: str
    due_mileage: int | None
    due_date: datetime | None
    status: str
    notes: str | None = None


@dataclass(slots=True)
class VehicleResolveRequest:
    vin: str | None = None
    customer_id: UUID | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    create_if_missing: bool = False


@dataclass(slots=True)
class VehicleResolveResult:
    vehicle: VehicleRecord | None
    repair_history: list[RepairRecord] = field(default_factory=list)
    maintenance_timeline: list[MaintenanceItem] = field(default_factory=list)
    action: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)
    # AI Decision Layer — proposed mutation; Workflow executes it
    decision: Any | None = None
