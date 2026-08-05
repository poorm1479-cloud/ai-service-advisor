"""Inspection Intelligence models — decide-only analysis inputs/outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4


class FindingSeverity(StrEnum):
    INFO = "info"
    OPTIONAL = "optional"
    RECOMMENDED = "recommended"
    SAFETY = "safety"
    CRITICAL = "critical"


class RepairPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass(slots=True)
class InspectionFinding:
    id: UUID = field(default_factory=uuid4)
    code: str = ""
    system: str = "general"
    title: str = ""
    description: str = ""
    severity: FindingSeverity = FindingSeverity.RECOMMENDED
    measured_value: str | None = None
    recommended_service: str | None = None
    estimated_cost: Decimal = Decimal("0.00")
    photos: list[str] = field(default_factory=list)
    technician_notes: str = ""


@dataclass(slots=True)
class InspectionRecord:
    """Stored technician inspection result."""

    id: UUID = field(default_factory=uuid4)
    shop_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    technician_id: UUID | None = None
    checklist_id: str | None = None
    findings: list[InspectionFinding] = field(default_factory=list)
    mileage: int | None = None
    vehicle_summary: dict[str, Any] = field(default_factory=dict)
    raw_notes: str = ""
    status: Literal["draft", "completed", "communicated"] = "completed"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InspectionContext:
    """Context for Inspection Intelligence (AI decide-only)."""

    shop_id: UUID
    inspection: InspectionRecord | None = None
    inspection_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    findings: list[InspectionFinding] = field(default_factory=list)
    channel: str = "sms"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InspectionPlan:
    """Bundle of Decision Objects from inspection analysis."""

    inspection_id: UUID | None
    decisions: list[Any] = field(default_factory=list)
    advisor_notes: list[str] = field(default_factory=list)
    safety_issue_count: int = 0
    recommended_count: int = 0
    optional_count: int = 0
    estimated_total: Decimal = Decimal("0.00")
    dashboard: dict[str, Any] = field(default_factory=dict)
