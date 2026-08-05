"""Analytics Engine HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.analytics.enums import ExportFormat, ReportType
from app.analytics.factory import AnalyticsRuntime, get_analytics_runtime

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


def _runtime() -> AnalyticsRuntime:
    return get_analytics_runtime()


class KpiOut(BaseModel):
    id: str
    label: str
    value: float
    unit: str
    delta_pct: float
    trend: str
    target: float | None = None
    benchmark: float | None = None
    vs_benchmark_pct: float | None = None
    detail: str | None = None


class PointOut(BaseModel):
    label: str
    value: float
    secondary: float | None = None


class ChartOut(BaseModel):
    id: str
    title: str
    points: list[PointOut]
    unit: str | None = None


class ForecastPointOut(BaseModel):
    period: str
    predicted: float
    low: float
    high: float


class ForecastOut(BaseModel):
    kpi: str
    horizon_days: int
    method: str
    points: list[ForecastPointOut]
    summary: str


class BenchmarkOut(BaseModel):
    kpi: str
    label: str
    shop_value: float
    industry_avg: float
    top_quartile: float
    unit: str
    status: str


class DashboardOut(BaseModel):
    shop_id: UUID
    generated_at: datetime
    period_start: date
    period_end: date
    version: int
    kpis: list[KpiOut]
    charts: list[ChartOut]
    forecasts: list[ForecastOut]
    benchmarks: list[BenchmarkOut]
    sources: dict[str, Any] = Field(default_factory=dict)


class ReportCreate(BaseModel):
    report_type: ReportType = ReportType.FULL
    title: str | None = None
    period_days: int = Field(30, ge=7, le=365)


class SectionOut(BaseModel):
    id: str
    title: str
    body: str
    metrics: list[dict[str, Any]] = Field(default_factory=list)


class ReportOut(BaseModel):
    id: UUID
    shop_id: UUID
    report_type: str
    title: str
    generated_at: datetime
    period_start: date
    period_end: date
    summary: str
    sections: list[SectionOut]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.CSV
    period_days: int = Field(30, ge=7, le=365)
    report_id: UUID | None = None


class ExportOut(BaseModel):
    id: UUID
    shop_id: UUID
    format: str
    filename: str
    content_type: str
    row_count: int
    created_at: datetime
    report_id: UUID | None = None
    preview: str | None = None


def _dashboard_out(snap) -> DashboardOut:
    return DashboardOut(
        shop_id=snap.shop_id,
        generated_at=snap.generated_at,
        period_start=snap.period_start,
        period_end=snap.period_end,
        version=snap.version,
        kpis=[
            KpiOut(
                id=k.id.value,
                label=k.label,
                value=k.value,
                unit=k.unit,
                delta_pct=k.delta_pct,
                trend=k.trend.value,
                target=k.target,
                benchmark=k.benchmark,
                vs_benchmark_pct=k.vs_benchmark_pct,
                detail=k.detail,
            )
            for k in snap.kpis
        ],
        charts=[
            ChartOut(
                id=c.id,
                title=c.title,
                unit=c.unit,
                points=[PointOut(label=p.label, value=p.value, secondary=p.secondary) for p in c.points],
            )
            for c in snap.charts
        ],
        forecasts=[
            ForecastOut(
                kpi=f.kpi.value,
                horizon_days=f.horizon_days,
                method=f.method,
                summary=f.summary,
                points=[
                    ForecastPointOut(period=p.period, predicted=p.predicted, low=p.low, high=p.high)
                    for p in f.points
                ],
            )
            for f in snap.forecasts
        ],
        benchmarks=[
            BenchmarkOut(
                kpi=b.kpi.value,
                label=b.label,
                shop_value=b.shop_value,
                industry_avg=b.industry_avg,
                top_quartile=b.top_quartile,
                unit=b.unit,
                status=b.status,
            )
            for b in snap.benchmarks
        ],
        sources=snap.sources,
    )


def _report_out(r) -> ReportOut:
    return ReportOut(
        id=r.id,
        shop_id=r.shop_id,
        report_type=r.report_type.value,
        title=r.title,
        generated_at=r.generated_at,
        period_start=r.period_start,
        period_end=r.period_end,
        summary=r.summary,
        sections=[SectionOut(id=s.id, title=s.title, body=s.body, metrics=s.metrics) for s in r.sections],
        metadata=r.metadata,
    )


def _export_out(a, *, include_preview: bool = True) -> ExportOut:
    preview = None
    if include_preview:
        preview = a.body[:1200] + ("…" if len(a.body) > 1200 else "")
    return ExportOut(
        id=a.id,
        shop_id=a.shop_id,
        format=a.format.value,
        filename=a.filename,
        content_type=a.content_type,
        row_count=a.row_count,
        created_at=a.created_at,
        report_id=a.report_id,
        preview=preview,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    period_days: int = Query(30, ge=7, le=365),
    forecast_horizon: int = Query(30, ge=7, le=90),
    force: bool = False,
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> DashboardOut:
    snap = rt.service.dashboard(
        user.shop_id,
        period_days=period_days,
        forecast_horizon=forecast_horizon,
        force=force,
    )
    return _dashboard_out(snap)


@router.post("/dashboard/refresh", response_model=DashboardOut)
async def refresh_dashboard(
    period_days: int = Query(30, ge=7, le=365),
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> DashboardOut:
    return _dashboard_out(rt.service.refresh(user.shop_id, period_days=period_days))


@router.post("/reports", response_model=ReportOut)
async def create_report(
    body: ReportCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> ReportOut:
    report = rt.service.create_report(
        user.shop_id,
        report_type=body.report_type,
        title=body.title,
        period_days=body.period_days,
    )
    return _report_out(report)


@router.get("/reports", response_model=list[ReportOut])
async def list_reports(
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> list[ReportOut]:
    return [_report_out(r) for r in rt.service.list_reports(user.shop_id, limit=limit)]


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> ReportOut:
    report = rt.service.get_report(user.shop_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_out(report)


@router.post("/exports", response_model=ExportOut)
async def create_export(
    body: ExportRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> ExportOut:
    try:
        if body.report_id:
            artifact = rt.service.export_report(user.shop_id, body.report_id, fmt=body.format)
        else:
            artifact = rt.service.export_dashboard(
                user.shop_id,
                fmt=body.format,
                period_days=body.period_days,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _export_out(artifact)


@router.get("/exports", response_model=list[ExportOut])
async def list_exports(
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> list[ExportOut]:
    return [_export_out(a) for a in rt.service.list_exports(user.shop_id, limit=limit)]


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> Response:
    artifact = rt.service.get_export(user.shop_id, export_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return Response(
        content=artifact.body,
        media_type=artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.get("/metrics/summary")
async def metrics_summary(
    user: CurrentUser = Depends(get_current_user),
    rt: AnalyticsRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return rt.service.metrics()
