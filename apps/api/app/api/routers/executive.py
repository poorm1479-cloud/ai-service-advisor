"""Executive Dashboard HTTP API — realtime polling + SSE."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.executive.factory import ExecutiveRuntime, get_executive_runtime

router = APIRouter(prefix="/v1/executive", tags=["executive"])


def _runtime() -> ExecutiveRuntime:
    return get_executive_runtime()


class CardOut(BaseModel):
    id: str
    label: str
    value: str
    delta: float | None = None
    unit: str | None = None
    tone: str = "neutral"
    detail: str | None = None


class ChartPointOut(BaseModel):
    label: str
    value: float
    secondary: float | None = None


class ChartOut(BaseModel):
    id: str
    title: str
    points: list[ChartPointOut]
    unit: str | None = None


class WidgetItemOut(BaseModel):
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
    items: list[WidgetItemOut]


class DashboardOut(BaseModel):
    shop_id: UUID
    generated_at: datetime
    version: int
    cards: list[CardOut]
    charts: list[ChartOut]
    widgets: list[WidgetOut]
    live: dict[str, Any]
    sources: dict[str, Any] = Field(default_factory=dict)


def _out(snap) -> DashboardOut:
    return DashboardOut(
        shop_id=snap.shop_id,
        generated_at=snap.generated_at,
        version=snap.version,
        cards=[
            CardOut(
                id=c.id,
                label=c.label,
                value=c.value,
                delta=c.delta,
                unit=c.unit,
                tone=c.tone,
                detail=c.detail,
            )
            for c in snap.cards
        ],
        charts=[
            ChartOut(
                id=ch.id,
                title=ch.title,
                unit=ch.unit,
                points=[
                    ChartPointOut(label=p.label, value=p.value, secondary=p.secondary)
                    for p in ch.points
                ],
            )
            for ch in snap.charts
        ],
        widgets=[
            WidgetOut(
                id=w.id,
                title=w.title,
                items=[
                    WidgetItemOut(
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
            for w in snap.widgets
        ],
        live=snap.live,
        sources=snap.sources,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def get_executive_dashboard(
    force: bool = Query(False),
    user: CurrentUser = Depends(get_current_user),
    rt: ExecutiveRuntime = Depends(_runtime),
) -> DashboardOut:
    existing = rt.store.get_snapshot(user.shop_id)
    snap = await rt.service.get_dashboard(user.shop_id, force=force)
    if existing and existing.version == snap.version and not force:
        rt.monitor.record_cache_hit()
    else:
        rt.monitor.record_refresh()
    rt.monitor.record_poll()
    return _out(snap)


@router.post("/refresh", response_model=DashboardOut)
async def refresh_executive_dashboard(
    user: CurrentUser = Depends(get_current_user),
    rt: ExecutiveRuntime = Depends(_runtime),
) -> DashboardOut:
    snap = await rt.service.get_dashboard(user.shop_id, force=True)
    rt.monitor.record_refresh()
    return _out(snap)


@router.get("/stream")
async def stream_executive_dashboard(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    rt: ExecutiveRuntime = Depends(_runtime),
) -> StreamingResponse:
    """Server-Sent Events stream — pushes snapshot when version changes."""

    async def event_generator():
        last_version = -1
        while True:
            if await request.is_disconnected():
                break
            snap = await rt.service.get_dashboard(user.shop_id, force=False, max_age_seconds=3)
            rt.monitor.record_poll()
            if snap.version != last_version:
                last_version = snap.version
                payload = _out(snap).model_dump(mode="json")
                yield f"event: dashboard\ndata: {json.dumps(payload)}\n\n"
            else:
                yield f"event: ping\ndata: {json.dumps({'version': snap.version})}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/metrics/summary")
async def executive_metrics(
    _: CurrentUser = Depends(get_current_user),
    rt: ExecutiveRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return rt.monitor.snapshot()
