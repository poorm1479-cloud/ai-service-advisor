"""Analytics domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.analytics.enums import ExportFormat, KpiId, ReportType, TrendDirection


@dataclass(slots=True)
class KpiMetric:
    id: KpiId
    label: str
    value: float
    unit: str
    delta_pct: float = 0.0
    trend: TrendDirection = TrendDirection.FLAT
    target: float | None = None
    benchmark: float | None = None
    vs_benchmark_pct: float | None = None
    detail: str | None = None


@dataclass(slots=True)
class SeriesPoint:
    label: str
    value: float
    secondary: float | None = None


@dataclass(slots=True)
class ChartSeries:
    id: str
    title: str
    points: list[SeriesPoint] = field(default_factory=list)
    unit: str | None = None


@dataclass(slots=True)
class ForecastPoint:
    period: str
    predicted: float
    low: float
    high: float


@dataclass(slots=True)
class ForecastResult:
    kpi: KpiId
    horizon_days: int
    method: str
    points: list[ForecastPoint] = field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class BenchmarkRow:
    kpi: KpiId
    label: str
    shop_value: float
    industry_avg: float
    top_quartile: float
    unit: str
    status: str  # ahead | on_par | behind


@dataclass(slots=True)
class AnalyticsSnapshot:
    shop_id: UUID
    generated_at: datetime
    period_start: date
    period_end: date
    kpis: list[KpiMetric] = field(default_factory=list)
    charts: list[ChartSeries] = field(default_factory=list)
    forecasts: list[ForecastResult] = field(default_factory=list)
    benchmarks: list[BenchmarkRow] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)
    version: int = 1


@dataclass(slots=True)
class ReportSection:
    id: str
    title: str
    body: str
    metrics: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AnalyticsReport:
    id: UUID
    shop_id: UUID
    report_type: ReportType
    title: str
    generated_at: datetime
    period_start: date
    period_end: date
    sections: list[ReportSection] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.id is None:  # type: ignore[unreachable]
            self.id = uuid4()


@dataclass(slots=True)
class ExportArtifact:
    id: UUID
    shop_id: UUID
    format: ExportFormat
    filename: str
    content_type: str
    body: str
    created_at: datetime
    report_id: UUID | None = None
    row_count: int = 0


@dataclass(slots=True)
class ShopMetricFact:
    """Raw daily fact used by the analytics engine (seedable / ingestible)."""

    shop_id: UUID
    day: date
    revenue: Decimal = Decimal("0")
    repair_orders: int = 0
    customers_active: int = 0
    customers_returning: int = 0
    appointments_offered: int = 0
    appointments_booked: int = 0
    marketing_spend: Decimal = Decimal("0")
    marketing_revenue: Decimal = Decimal("0")
    mechanic_hours: float = 0.0
    billed_hours: float = 0.0
    ai_conversations: int = 0
    ai_resolved: int = 0
    clv_cohort_avg: Decimal = Decimal("0")
