"""Owner Dashboard service — read-only orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.dashboard.aggregation import DashboardAggregator
from app.dashboard.metrics import performance_from_sources, system_health_from_sources
from app.dashboard.models import OwnerDashboardSnapshot
from app.dashboard.widgets import build_daily_summary, build_widgets


class DashboardService:
    """AI Operations Center — aggregates read-only views for shop owners."""

    def __init__(self, aggregator: DashboardAggregator | None = None) -> None:
        self._aggregator = aggregator or DashboardAggregator()
        self._cache: dict[UUID, tuple[float, OwnerDashboardSnapshot]] = {}
        self._version: dict[UUID, int] = {}
        self._ttl_sec = 5.0

    async def get_snapshot(self, shop_id: UUID, *, force: bool = False) -> OwnerDashboardSnapshot:
        import time

        now_ts = time.monotonic()
        if not force and shop_id in self._cache:
            cached_at, snap = self._cache[shop_id]
            if now_ts - cached_at < self._ttl_sec:
                return snap

        sources = await self._aggregator.collect(shop_id)
        performance = performance_from_sources(sources)
        health = system_health_from_sources(sources)
        widgets = build_widgets(sources)
        summary = build_daily_summary(sources, performance)
        version = self._version.get(shop_id, 0) + 1
        self._version[shop_id] = version
        snap = OwnerDashboardSnapshot(
            shop_id=shop_id,
            generated_at=datetime.now(timezone.utc),
            version=version,
            summary=summary,
            widgets=widgets,
            performance=performance,
            system_health=health,
            sources=sources,
            read_only=True,
        )
        self._cache[shop_id] = (now_ts, snap)
        return snap

    async def daily_summary(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        return {"summary": snap.summary, "generated_at": snap.generated_at.isoformat(), "read_only": True}

    async def ai_activity(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        widget = next((w for w in snap.widgets if w.id == "ai_employee_summary"), None)
        return {
            "widget": widget,
            "voice": (snap.sources or {}).get("voice"),
            "conversation": (snap.sources or {}).get("conversation"),
            "read_only": True,
        }

    async def pending_actions(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        ids = {"approval_queue", "customer_followup_queue", "ai_escalation_queue"}
        widgets = [w for w in snap.widgets if w.id in ids]
        return {"widgets": widgets, "read_only": True}

    async def revenue_opportunities(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        widget = next((w for w in snap.widgets if w.id == "revenue_opportunities"), None)
        return {
            "widget": widget,
            "revenue": (snap.sources or {}).get("revenue"),
            "read_only": True,
        }

    async def customer_risk(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        esc = next((w for w in snap.widgets if w.id == "ai_escalation_queue"), None)
        follow = next((w for w in snap.widgets if w.id == "customer_followup_queue"), None)
        return {"escalations": esc, "followups": follow, "read_only": True}

    async def appointment_overview(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        widget = next((w for w in snap.widgets if w.id == "todays_appointments"), None)
        return {
            "widget": widget,
            "scheduling": (snap.sources or {}).get("scheduling"),
            "read_only": True,
        }

    async def workflow_status(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        widget = next((w for w in snap.widgets if w.id == "workflow_monitor"), None)
        return {
            "widget": widget,
            "workflow": (snap.sources or {}).get("workflow"),
            "read_only": True,
        }

    async def performance_metrics(self, shop_id: UUID) -> dict[str, Any]:
        snap = await self.get_snapshot(shop_id)
        return {
            "performance": snap.performance,
            "system_health": snap.system_health,
            "widget": next((w for w in snap.widgets if w.id == "performance_metrics"), None),
            "read_only": True,
        }
