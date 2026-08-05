"""Revenue intelligence domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.revenue_intel.enums import (
    ContactChannel,
    HealthBand,
    JobStatus,
    OpportunityHorizon,
    OpportunityKind,
    OpportunityStatus,
)


@dataclass(slots=True)
class RepairSnapshot:
    service_type: str
    description: str = ""
    cost: Decimal = Decimal("0")
    mileage: int | None = None
    performed_at: datetime | None = None
    recommendation: str | None = None
    declined: bool = False


@dataclass(slots=True)
class CommunicationSnapshot:
    channel: str
    direction: str
    message: str
    occurred_at: datetime | None = None


@dataclass(slots=True)
class VehicleSnapshot:
    id: UUID
    vin: str
    year: int
    make: str
    model: str
    mileage: int
    license_plate: str | None = None
    repairs: list[RepairSnapshot] = field(default_factory=list)


@dataclass(slots=True)
class CustomerSnapshot:
    id: UUID
    shop_id: UUID
    name: str
    phone: str | None = None
    email: str | None = None
    vehicles: list[VehicleSnapshot] = field(default_factory=list)
    communications: list[CommunicationSnapshot] = field(default_factory=list)
    declined_estimates: list[dict[str, Any]] = field(default_factory=list)
    last_visit_at: datetime | None = None
    first_visit_at: datetime | None = None
    total_spend: Decimal = Decimal("0")
    visit_count: int = 0


@dataclass(slots=True)
class HealthScore:
    entity_id: UUID
    entity_type: str
    score: float
    band: HealthBand
    factors: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Opportunity:
    id: UUID
    shop_id: UUID
    customer_id: UUID
    vehicle_id: UUID | None
    kind: OpportunityKind
    horizon: OpportunityHorizon
    title: str
    reason: str
    expected_revenue: Decimal
    probability: float
    expected_roi: float
    recommended_contact_date: date
    recommended_channel: ContactChannel
    recommended_message: str
    customer_name: str = ""
    vehicle_label: str | None = None
    customer_health: float | None = None
    vehicle_health: float | None = None
    status: OpportunityStatus = OpportunityStatus.OPEN
    seasonality_boost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    analysis_job_id: UUID | None = None


@dataclass(slots=True)
class ForecastPoint:
    period_start: date
    period_end: date
    expected_revenue: Decimal
    opportunity_count: int
    win_probability_avg: float
    label: str = ""


@dataclass(slots=True)
class MonthlyForecast:
    shop_id: UUID
    as_of: date
    months: list[ForecastPoint] = field(default_factory=list)
    total_expected: Decimal = Decimal("0")


@dataclass(slots=True)
class RoiPoint:
    label: str
    invested: Decimal
    expected_return: Decimal
    roi: float
    opportunity_count: int = 0


@dataclass(slots=True)
class DashboardSummary:
    shop_id: UUID
    as_of: datetime
    expected_revenue_daily: Decimal
    expected_revenue_weekly: Decimal
    expected_revenue_monthly: Decimal
    open_opportunities: int
    lost_customers: int
    maintenance_overdue: int
    avg_customer_health: float
    avg_vehicle_health: float
    avg_probability: float
    avg_roi: float
    top_kinds: list[dict[str, Any]] = field(default_factory=list)
    roi_series: list[RoiPoint] = field(default_factory=list)
    forecast: MonthlyForecast | None = None


@dataclass(slots=True)
class AnalysisJob:
    id: UUID
    shop_id: UUID
    status: JobStatus = JobStatus.PENDING
    customers_analyzed: int = 0
    opportunities_created: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NightlyReport:
    job: AnalysisJob
    opportunities: list[Opportunity]
    customer_scores: list[HealthScore]
    vehicle_scores: list[HealthScore]
    forecast: MonthlyForecast
    dashboard: DashboardSummary
