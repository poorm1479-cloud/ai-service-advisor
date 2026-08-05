"""Scheduling intelligence domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class BusinessHours:
    weekday: int  # 0=Mon .. 6=Sun
    open_time: time
    close_time: time
    closed: bool = False


@dataclass(slots=True)
class MechanicSkill:
    repair_type: str
    proficiency: int = 3  # 1-5
    avg_minutes: int | None = None


@dataclass(slots=True)
class Mechanic:
    id: UUID
    shop_id: UUID
    name: str
    skills: list[MechanicSkill] = field(default_factory=list)
    work_start: time = time(8, 0)
    work_end: time = time(17, 0)
    workdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    active: bool = True
    hourly_rate: Decimal = Decimal("75.00")
    # From Team membership — used only as a soft auto-assign tie-break.
    role: str = "staff"


@dataclass(slots=True)
class Bay:
    id: UUID
    shop_id: UUID
    name: str
    bay_type: str = "general"  # general | alignment | quick_service | heavy
    supports_vehicle_types: list[str] = field(default_factory=lambda: ["sedan", "suv", "truck", "van", "ev", "other"])
    active: bool = True


@dataclass(slots=True)
class Appointment:
    id: UUID
    shop_id: UUID
    start: datetime
    end: datetime
    status: str = "booked"
    priority: str = "normal"
    repair_type: str = "general"
    vehicle_type: str = "sedan"
    estimated_duration_min: int = 60
    service_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    mechanic_id: UUID | None = None
    bay_id: UUID | None = None
    walk_in_id: UUID | None = None
    source: str = "dashboard"
    notes: str | None = None
    estimated_revenue: Decimal = Decimal("0.00")
    estimated_completion: datetime | None = None
    wait_time_min: int | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SlotCandidate:
    start: datetime
    end: datetime
    mechanic_id: UUID | None
    bay_id: UUID | None
    score: float
    reasons: list[str] = field(default_factory=list)
    estimated_wait_min: int = 0
    estimated_completion: datetime | None = None


@dataclass(slots=True)
class ConflictReport:
    has_conflict: bool
    conflicts: list[str] = field(default_factory=list)
    overbooked: bool = False
    severity: str = "none"  # none | low | medium | high


@dataclass(slots=True)
class CapacityForecast:
    day: date
    total_minutes: int
    booked_minutes: int
    utilization: float
    remaining_slots: int
    overbook_risk: float
    expected_wait_min: float
    expected_revenue: Decimal


@dataclass(slots=True)
class OptimizedSchedule:
    shop_id: UUID
    day: date
    appointments: list[Appointment]
    improvements: list[str] = field(default_factory=list)
    mechanic_utilization: dict[str, float] = field(default_factory=dict)
    bay_utilization: dict[str, float] = field(default_factory=dict)
    expected_daily_revenue: Decimal = Decimal("0.00")
    avg_customer_wait_min: float = 0.0
    conflicts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BookingRequest:
    shop_id: UUID
    preferred_start: datetime | None = None
    preferred_end: datetime | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    service_id: UUID | None = None
    service_name: str | None = None
    repair_type: str = "general"  # required skill (from catalog service.skill)
    required_bay: str | None = None  # required bay type (from catalog service.bay)
    vehicle_type: str = "sedan"
    priority: str = "normal"
    estimated_duration_min: int | None = None
    source: str = "dashboard"
    notes: str | None = None
    walk_in_id: UUID | None = None
    mechanic_id: UUID | None = None
    bay_id: UUID | None = None
    estimated_revenue: Decimal | None = None


@dataclass(slots=True)
class BookingResult:
    success: bool
    appointment: Appointment | None = None
    recommended_slot: SlotCandidate | None = None
    alternatives: list[SlotCandidate] = field(default_factory=list)
    conflicts: ConflictReport | None = None
    message: str | None = None
    ai_decisions: dict[str, Any] = field(default_factory=dict)
