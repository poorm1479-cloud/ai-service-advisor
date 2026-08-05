"""Revenue agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.agents.vehicle.models import MaintenanceItem, RepairRecord, VehicleRecord


@dataclass(slots=True)
class RevenueAnalysisRequest:
    customer_id: UUID | None = None
    vehicle: VehicleRecord | None = None
    repair_history: list[RepairRecord] = field(default_factory=list)
    maintenance_timeline: list[MaintenanceItem] = field(default_factory=list)
    intent: str | None = None
    declined_estimates: list[dict[str, Any]] = field(default_factory=list)
    days_since_last_visit: int | None = None


@dataclass(slots=True)
class UpsellOpportunity:
    service: str
    reason: str
    estimated_revenue: Decimal
    priority: str = "medium"


@dataclass(slots=True)
class RevenueInsights:
    upsell_opportunities: list[UpsellOpportunity] = field(default_factory=list)
    declined_estimates: list[dict[str, Any]] = field(default_factory=list)
    maintenance_reminders: list[dict[str, Any]] = field(default_factory=list)
    lost_customer_risk: float = 0.0
    predicted_revenue: Decimal = Decimal("0.00")
    notes: list[str] = field(default_factory=list)
    # AI Decision Layer wrap
    decision: Any | None = None
