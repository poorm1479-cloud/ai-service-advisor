"""Revenue Intelligence HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.revenue_intel.enums import OpportunityHorizon, OpportunityKind, OpportunityStatus
from app.revenue_intel.factory import RevenueIntelRuntime, get_revenue_intel_runtime

router = APIRouter(prefix="/v1/revenue", tags=["revenue"])


def _runtime() -> RevenueIntelRuntime:
    return get_revenue_intel_runtime()


class OpportunityOut(BaseModel):
    id: UUID
    shop_id: UUID
    customer_id: UUID
    vehicle_id: UUID | None
    kind: str
    horizon: str
    title: str
    reason: str
    expected_revenue: str
    probability: float
    expected_roi: float
    recommended_contact_date: date
    recommended_channel: str
    recommended_message: str
    customer_name: str
    vehicle_label: str | None
    customer_health: float | None
    vehicle_health: float | None
    status: str
    seasonality_boost: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None


class RoiPointOut(BaseModel):
    label: str
    invested: str
    expected_return: str
    roi: float
    opportunity_count: int


class ForecastPointOut(BaseModel):
    period_start: date
    period_end: date
    expected_revenue: str
    opportunity_count: int
    win_probability_avg: float
    label: str


class ForecastOut(BaseModel):
    shop_id: UUID
    as_of: date
    months: list[ForecastPointOut]
    total_expected: str


class DashboardOut(BaseModel):
    shop_id: UUID
    as_of: datetime
    expected_revenue_daily: str
    expected_revenue_weekly: str
    expected_revenue_monthly: str
    open_opportunities: int
    lost_customers: int
    maintenance_overdue: int
    avg_customer_health: float
    avg_vehicle_health: float
    avg_probability: float
    avg_roi: float
    top_kinds: list[dict[str, Any]]
    roi_series: list[RoiPointOut]
    forecast: ForecastOut | None


class HealthScoreOut(BaseModel):
    entity_id: UUID
    entity_type: str
    score: float
    band: str
    factors: dict[str, float]
    notes: list[str]


class JobOut(BaseModel):
    id: UUID
    shop_id: UUID
    status: str
    customers_analyzed: int
    opportunities_created: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    summary: dict[str, Any]


class StatusUpdate(BaseModel):
    status: OpportunityStatus


def _opp_out(o) -> OpportunityOut:
    return OpportunityOut(
        id=o.id,
        shop_id=o.shop_id,
        customer_id=o.customer_id,
        vehicle_id=o.vehicle_id,
        kind=o.kind.value,
        horizon=o.horizon.value,
        title=o.title,
        reason=o.reason,
        expected_revenue=str(o.expected_revenue),
        probability=o.probability,
        expected_roi=o.expected_roi,
        recommended_contact_date=o.recommended_contact_date,
        recommended_channel=o.recommended_channel.value,
        recommended_message=o.recommended_message,
        customer_name=o.customer_name,
        vehicle_label=o.vehicle_label,
        customer_health=o.customer_health,
        vehicle_health=o.vehicle_health,
        status=o.status.value,
        seasonality_boost=o.seasonality_boost,
        metadata=o.metadata,
        created_at=o.created_at,
    )


def _forecast_out(f) -> ForecastOut:
    return ForecastOut(
        shop_id=f.shop_id,
        as_of=f.as_of,
        months=[
            ForecastPointOut(
                period_start=m.period_start,
                period_end=m.period_end,
                expected_revenue=str(m.expected_revenue),
                opportunity_count=m.opportunity_count,
                win_probability_avg=m.win_probability_avg,
                label=m.label,
            )
            for m in f.months
        ],
        total_expected=str(f.total_expected),
    )


def _dashboard_out(d) -> DashboardOut:
    return DashboardOut(
        shop_id=d.shop_id,
        as_of=d.as_of,
        expected_revenue_daily=str(d.expected_revenue_daily),
        expected_revenue_weekly=str(d.expected_revenue_weekly),
        expected_revenue_monthly=str(d.expected_revenue_monthly),
        open_opportunities=d.open_opportunities,
        lost_customers=d.lost_customers,
        maintenance_overdue=d.maintenance_overdue,
        avg_customer_health=d.avg_customer_health,
        avg_vehicle_health=d.avg_vehicle_health,
        avg_probability=d.avg_probability,
        avg_roi=d.avg_roi,
        top_kinds=d.top_kinds,
        roi_series=[
            RoiPointOut(
                label=p.label,
                invested=str(p.invested),
                expected_return=str(p.expected_return),
                roi=p.roi,
                opportunity_count=p.opportunity_count,
            )
            for p in d.roi_series
        ],
        forecast=_forecast_out(d.forecast) if d.forecast else None,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> DashboardOut:
    # Auto-run if no opportunities yet
    open_opps = await rt.service.list_opportunities(user.shop_id, limit=1)
    if not open_opps:
        report = await rt.service.run_nightly_analysis(user.shop_id)
        kinds: dict[str, int] = {}
        for o in report.opportunities:
            kinds[o.kind.value] = kinds.get(o.kind.value, 0) + 1
        rt.monitor.record_nightly(
            customers=report.job.customers_analyzed,
            opportunities=report.job.opportunities_created,
            kinds=kinds,
        )
        return _dashboard_out(report.dashboard)
    dash = await rt.service.build_dashboard(user.shop_id)
    return _dashboard_out(dash)


@router.post("/analyze", response_model=JobOut)
async def run_analysis(
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> JobOut:
    try:
        report = await rt.service.run_nightly_analysis(user.shop_id)
    except Exception as exc:  # noqa: BLE001
        rt.monitor.record_failure()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    kinds: dict[str, int] = {}
    for o in report.opportunities:
        kinds[o.kind.value] = kinds.get(o.kind.value, 0) + 1
    rt.monitor.record_nightly(
        customers=report.job.customers_analyzed,
        opportunities=report.job.opportunities_created,
        kinds=kinds,
    )
    j = report.job
    return JobOut(
        id=j.id,
        shop_id=j.shop_id,
        status=j.status.value,
        customers_analyzed=j.customers_analyzed,
        opportunities_created=j.opportunities_created,
        started_at=j.started_at,
        finished_at=j.finished_at,
        error=j.error,
        summary=j.summary,
    )


@router.get("/opportunities", response_model=list[OpportunityOut])
async def list_opportunities(
    horizon: str | None = None,
    kind: str | None = None,
    status_filter: str | None = Query("open", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> list[OpportunityOut]:
    h = OpportunityHorizon(horizon) if horizon else None
    k = OpportunityKind(kind) if kind else None
    st = OpportunityStatus(status_filter) if status_filter else None
    items = await rt.service.list_opportunities(
        user.shop_id, horizon=h, kind=k, status=st, limit=limit
    )
    return [_opp_out(o) for o in items]


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
async def update_opportunity(
    opportunity_id: UUID,
    body: StatusUpdate,
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> OpportunityOut:
    try:
        opp = await rt.service.update_opportunity_status(
            user.shop_id, opportunity_id, body.status
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _opp_out(opp)


@router.get("/forecast", response_model=ForecastOut)
async def get_forecast(
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> ForecastOut:
    return _forecast_out(await rt.service.get_forecast(user.shop_id))


@router.get("/health", response_model=list[HealthScoreOut])
async def list_health(
    entity_type: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> list[HealthScoreOut]:
    scores = await rt.service.list_scores(user.shop_id, entity_type=entity_type)
    return [
        HealthScoreOut(
            entity_id=s.entity_id,
            entity_type=s.entity_type,
            score=s.score,
            band=s.band.value,
            factors=s.factors,
            notes=s.notes,
        )
        for s in scores
    ]


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    user: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> list[JobOut]:
    jobs = await rt.service.list_jobs(user.shop_id)
    return [
        JobOut(
            id=j.id,
            shop_id=j.shop_id,
            status=j.status.value,
            customers_analyzed=j.customers_analyzed,
            opportunities_created=j.opportunities_created,
            started_at=j.started_at,
            finished_at=j.finished_at,
            error=j.error,
            summary=j.summary,
        )
        for j in jobs
    ]


@router.get("/metrics/summary")
async def metrics(
    _: CurrentUser = Depends(get_current_user),
    rt: RevenueIntelRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return rt.monitor.snapshot()
