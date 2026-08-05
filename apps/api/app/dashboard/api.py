"""Owner Dashboard HTTP API — read-only AI Operations Center."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.api.deps import require_dashboard_access
from app.dashboard.factory import DashboardRuntime, get_dashboard_runtime

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


def _runtime() -> DashboardRuntime:
    return get_dashboard_runtime()


class MetricOut(BaseModel):
    key: str
    label: str
    value: Any
    unit: str | None = None
    tone: str = "neutral"
    detail: str | None = None


class QueueItemOut(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    status: str | None = None
    priority: str = "normal"
    href: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class WidgetOut(BaseModel):
    id: str
    title: str
    kind: str
    summary: str | None = None
    metrics: list[MetricOut] = Field(default_factory=list)
    items: list[QueueItemOut] = Field(default_factory=list)


class OwnerDashboardOut(BaseModel):
    shop_id: UUID
    generated_at: datetime
    version: int
    read_only: bool = True
    summary: dict[str, Any]
    performance: dict[str, Any]
    system_health: dict[str, Any]
    widgets: list[WidgetOut]
    sources: dict[str, Any] = Field(default_factory=dict)


def _widget_out(w) -> WidgetOut:
    return WidgetOut(
        id=w.id,
        title=w.title,
        kind=w.kind,
        summary=w.summary,
        metrics=[
            MetricOut(
                key=m.key,
                label=m.label,
                value=m.value,
                unit=m.unit,
                tone=m.tone,
                detail=m.detail,
            )
            for m in w.metrics
        ],
        items=[
            QueueItemOut(
                id=i.id,
                title=i.title,
                subtitle=i.subtitle,
                status=i.status,
                priority=i.priority,
                href=i.href,
                meta=i.meta,
            )
            for i in w.items
        ],
    )


def _out(snap) -> OwnerDashboardOut:
    return OwnerDashboardOut(
        shop_id=snap.shop_id,
        generated_at=snap.generated_at,
        version=snap.version,
        read_only=True,
        summary=snap.summary,
        performance=snap.performance,
        system_health=snap.system_health,
        widgets=[_widget_out(w) for w in snap.widgets],
        sources=snap.sources or {},
    )


@router.get("", response_model=OwnerDashboardOut)
@router.get("/", response_model=OwnerDashboardOut)
async def get_owner_dashboard(
    force: bool = Query(False),
    user: CurrentUser = Depends(require_dashboard_access()),
) -> OwnerDashboardOut:
    snap = await _runtime().service.get_snapshot(user.shop_id, force=force)
    return _out(snap)


@router.get("/summary")
async def get_daily_summary(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    return await _runtime().service.daily_summary(user.shop_id)


@router.get("/ai-activity")
async def get_ai_activity(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.ai_activity(user.shop_id)
    if data.get("widget"):
        data["widget"] = _widget_out(data["widget"])
    return data


@router.get("/pending-actions")
async def get_pending_actions(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.pending_actions(user.shop_id)
    data["widgets"] = [_widget_out(w) for w in data.get("widgets") or []]
    return data


@router.get("/revenue-opportunities")
async def get_revenue_opportunities(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.revenue_opportunities(user.shop_id)
    if data.get("widget"):
        data["widget"] = _widget_out(data["widget"])
    return data


@router.get("/customer-risk")
async def get_customer_risk(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.customer_risk(user.shop_id)
    for key in ("escalations", "followups"):
        if data.get(key):
            data[key] = _widget_out(data[key])
    return data


@router.get("/appointments")
async def get_appointment_overview(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.appointment_overview(user.shop_id)
    if data.get("widget"):
        data["widget"] = _widget_out(data["widget"])
    return data


@router.get("/workflows")
async def get_workflow_status(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.workflow_status(user.shop_id)
    if data.get("widget"):
        data["widget"] = _widget_out(data["widget"])
    return data


@router.get("/performance")
async def get_performance_metrics(user: CurrentUser = Depends(require_dashboard_access())) -> dict[str, Any]:
    data = await _runtime().service.performance_metrics(user.shop_id)
    if data.get("widget"):
        data["widget"] = _widget_out(data["widget"])
    return data
