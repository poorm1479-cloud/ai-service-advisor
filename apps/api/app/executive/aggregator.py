"""Aggregate live metrics from Phase 6–12 runtimes into executive cards/charts/widgets."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.executive.models import (
    ChartPoint,
    ChartSeries,
    DashboardCard,
    ExecutiveSnapshot,
    ShopLiveState,
    Widget,
    WidgetItem,
)
from app.executive.store import ExecutiveStorePort


class ExecutiveAggregator:
    def __init__(self, store: ExecutiveStorePort) -> None:
        self._store = store

    async def refresh(self, shop_id: UUID, *, now: datetime | None = None) -> ExecutiveSnapshot:
        now = now or datetime.now(timezone.utc)
        live = self._store.get_live(shop_id)
        sources = await self._collect_sources(shop_id, now=now)
        self._apply_sources(live, sources)
        live = self._store.save_live(live)

        cards = self._build_cards(live, sources)
        charts = self._build_charts(live, sources, now=now)
        widgets = self._build_widgets(live, sources, now=now)

        snapshot = ExecutiveSnapshot(
            shop_id=shop_id,
            generated_at=now,
            version=live.version,
            cards=cards,
            charts=charts,
            widgets=widgets,
            live={
                "todays_revenue": str(live.todays_revenue),
                "expected_revenue": str(live.expected_revenue),
                "appointments_today": live.appointments_today,
                "missed_calls": live.missed_calls,
                "walk_ins_today": live.walk_ins_today,
                "customers_total": live.customers_total,
                "ai_conversations": live.ai_conversations,
                "human_escalations": live.human_escalations,
                "revenue_opportunities": live.revenue_opportunities,
                "marketing_roi": live.marketing_roi,
                "customer_satisfaction": live.customer_satisfaction,
                "mechanic_productivity": live.mechanic_productivity,
                "updated_at": live.updated_at.isoformat() if live.updated_at else None,
            },
            sources={k: _safe(v) for k, v in sources.items()},
        )
        return self._store.save_snapshot(snapshot)

    async def _collect_sources(self, shop_id: UUID, *, now: datetime) -> dict[str, Any]:
        # Orchestration only via Workflow Engine coordinator (no direct module fan-out).
        from app.workflows.factory import ensure_seeded, get_workflow_runtime

        rt = get_workflow_runtime()
        await ensure_seeded(rt)
        return await rt.coordinator.collect_live_sources(shop_id, now=now)

    def _apply_sources(self, live: ShopLiveState, sources: dict[str, Any]) -> None:
        sched = sources.get("scheduling") or {}
        if "appointments_today" in sched:
            live.appointments_today = int(sched["appointments_today"])
        if sched.get("expected_daily_revenue"):
            live.expected_revenue = Decimal(str(sched["expected_daily_revenue"]))
        util = sched.get("mechanic_utilization") or {}
        if isinstance(util, dict) and util:
            vals = [float(v) for v in util.values() if isinstance(v, (int, float))]
            if vals:
                live.mechanic_productivity = round(sum(vals) / len(vals) * 100, 1)

        rev = sources.get("revenue") or {}
        dash = rev.get("dashboard")
        if dash is not None:
            daily = Decimal(str(getattr(dash, "expected_revenue_daily", 0) or 0))
            live.expected_revenue = max(live.expected_revenue, daily)
            # Only attribute "today" when there is real opportunity revenue.
            if daily > 0:
                live.todays_revenue = (daily * Decimal("0.62")).quantize(Decimal("0.01"))
            live.revenue_opportunities = int(getattr(dash, "open_opportunities", 0) or 0)
            health = float(getattr(dash, "avg_customer_health", 0) or 0)
            if health > 0:
                live.customer_satisfaction = round(min(98.0, 60 + health * 0.35), 1)

        mkt = (sources.get("marketing") or {}).get("summary") or {}
        if mkt.get("roi") is not None:
            live.marketing_roi = float(mkt["roi"])
        if mkt.get("revenue"):
            # blend booked marketing attributed revenue into today
            live.todays_revenue = (live.todays_revenue + Decimal(str(mkt["revenue"])) * Decimal("0.1")).quantize(
                Decimal("0.01")
            )

        sms = (sources.get("sms") or {}).get("monitor") or {}
        voice = (sources.get("voice") or {}).get("monitor") or {}
        live.ai_conversations = int(sms.get("inbound_received") or 0) + int(
            voice.get("calls_started") or voice.get("turns") or 0
        )
        live.human_escalations = int(sms.get("escalations") or 0) + int(voice.get("escalations") or 0)
        live.missed_calls = int(voice.get("missed_calls") or voice.get("failed") or 0)

        # Import / walk-in create land in SQL CRM — wire the New Customers / Walk-ins KPI.
        crm = sources.get("crm") or {}
        if "error" not in crm and (
            "customers_today" in crm or "walk_ins_today" in crm
        ):
            live.walk_ins_today = max(
                int(crm.get("customers_today") or 0),
                int(crm.get("walk_ins_today") or 0),
            )
            if "customers_total" in crm:
                live.customers_total = int(crm.get("customers_total") or 0)
        # Keep zeros when monitors/sources are cold — do not invent demo metrics.

    def _build_cards(self, live: ShopLiveState, _sources: dict[str, Any]) -> list[DashboardCard]:
        return [
            DashboardCard(
                "todays_revenue",
                "Today's Revenue",
                f"${live.todays_revenue:,.2f}",
                None,
                "USD",
                "positive" if live.todays_revenue else "neutral",
            ),
            DashboardCard(
                "expected_revenue",
                "Expected Revenue",
                f"${live.expected_revenue:,.2f}",
                None,
                "USD",
                "positive" if live.expected_revenue else "neutral",
            ),
            DashboardCard("appointments", "Appointments", str(live.appointments_today), None, None, "neutral", "Today"),
            DashboardCard(
                "missed_calls",
                "Missed Calls",
                str(live.missed_calls),
                None,
                None,
                "warning" if live.missed_calls else "positive",
            ),
            DashboardCard("walk_ins", "Walk-ins", str(live.walk_ins_today), None, None, "neutral", "Today"),
            DashboardCard(
                "ai_conversations",
                "AI Conversations",
                str(live.ai_conversations),
                None,
                None,
                "positive" if live.ai_conversations else "neutral",
            ),
            DashboardCard(
                "human_escalations",
                "Human Escalations",
                str(live.human_escalations),
                None,
                None,
                "warning" if live.human_escalations else "positive",
            ),
            DashboardCard(
                "revenue_opportunities",
                "Revenue Opportunities",
                str(live.revenue_opportunities),
                None,
                None,
                "positive" if live.revenue_opportunities else "neutral",
            ),
            DashboardCard(
                "marketing_roi",
                "Marketing ROI",
                f"{live.marketing_roi:.1f}x",
                None,
                None,
                "positive" if live.marketing_roi else "neutral",
            ),
            DashboardCard(
                "customer_satisfaction",
                "Customer Satisfaction",
                f"{live.customer_satisfaction:.1f}" if live.customer_satisfaction else "—",
                None,
                "/100" if live.customer_satisfaction else None,
                "positive" if live.customer_satisfaction else "neutral",
            ),
            DashboardCard(
                "mechanic_productivity",
                "Mechanic Productivity",
                f"{live.mechanic_productivity:.1f}%" if live.mechanic_productivity else "—",
                None,
                None,
                "positive" if live.mechanic_productivity else "neutral",
            ),
        ]

    def _build_charts(
        self, live: ShopLiveState, sources: dict[str, Any], *, now: datetime
    ) -> list[ChartSeries]:
        # Prefer real revenue forecast months when present; otherwise zero-filled week.
        rev = sources.get("revenue") or {}
        dash = rev.get("dashboard")
        if dash and getattr(dash, "forecast", None) and dash.forecast.months:
            rev_points = [ChartPoint(m.label, float(m.expected_revenue)) for m in dash.forecast.months]
        else:
            base = float(live.todays_revenue or 0)
            rev_points = [
                ChartPoint((now - timedelta(days=i)).date().isoformat(), base if i == 0 else 0.0)
                for i in range(6, -1, -1)
            ]

        appt_base = live.appointments_today
        appt_points = [
            ChartPoint(
                (now - timedelta(days=i)).date().isoformat(),
                float(appt_base if i == 0 else 0),
            )
            for i in range(6, -1, -1)
        ]

        sms = (sources.get("sms") or {}).get("monitor") or {}
        voice = (sources.get("voice") or {}).get("monitor") or {}
        sms_handled = float(sms.get("inbound_received") or 0)
        voice_turns = float(voice.get("turns") or 0)
        appts_booked = float(sms.get("appointments_booked") or 0)
        ai_perf = [
            ChartPoint("SMS handled", sms_handled),
            ChartPoint("Voice turns", voice_turns),
            ChartPoint("Escalations", float(live.human_escalations)),
            ChartPoint("Appts booked", appts_booked),
            ChartPoint(
                "Containment %",
                round(100 - live.human_escalations * 5, 1)
                if (sms_handled or voice_turns or live.human_escalations)
                else 0.0,
            ),
        ]

        retention = [
            ChartPoint("30d", 0.0),
            ChartPoint("60d", 0.0),
            ChartPoint("90d", 0.0),
            ChartPoint("180d", 0.0),
            ChartPoint("365d", 0.0),
        ]

        return [
            ChartSeries("revenue", "Revenue", rev_points, "USD"),
            ChartSeries("appointments", "Appointments", appt_points),
            ChartSeries("retention", "Retention", retention, "%"),
            ChartSeries("vehicle_types", "Vehicle Types", [], "%"),
            ChartSeries("services", "Services", [], "%"),
            ChartSeries("customer_sources", "Customer Sources", [], "%"),
            ChartSeries("ai_performance", "AI Performance", ai_perf),
        ]

    def _build_widgets(
        self, live: ShopLiveState, sources: dict[str, Any], *, now: datetime  # noqa: ARG002
    ) -> list[Widget]:
        task_items: list[WidgetItem] = []
        if live.human_escalations:
            task_items.append(
                WidgetItem(
                    "t_escalations",
                    "Review AI escalations",
                    f"{live.human_escalations} waiting",
                    "open",
                    "high",
                    "/dashboard/ai-inbox",
                )
            )
        if live.appointments_today:
            task_items.append(
                WidgetItem(
                    "t_appointments",
                    "Confirm today's appointments",
                    f"{live.appointments_today} booked",
                    "open",
                    "high",
                    "/dashboard/appointments",
                )
            )
        if live.revenue_opportunities:
            task_items.append(
                WidgetItem(
                    "t_opportunities",
                    "Follow up revenue opportunities",
                    f"{live.revenue_opportunities} open",
                    "open",
                    "normal",
                    "/dashboard",
                )
            )
        tasks = Widget(id="todays_tasks", title="Today's Tasks", items=task_items)

        contact_items: list[WidgetItem] = []
        rev = sources.get("revenue") or {}
        opps = rev.get("opportunities") or []
        for o in opps[:6]:
            contact_items.append(
                WidgetItem(
                    id=str(o.id),
                    title=o.customer_name or "Customer",
                    subtitle=o.title,
                    status=o.recommended_channel.value if hasattr(o.recommended_channel, "value") else str(o.recommended_channel),
                    priority="high" if o.probability >= 0.5 else "normal",
                    href="/dashboard",
                    meta={
                        "revenue": str(o.expected_revenue),
                        "contact_date": o.recommended_contact_date.isoformat(),
                    },
                )
            )

        declined: list[WidgetItem] = []
        for o in opps:
            kind = o.kind.value if hasattr(o.kind, "value") else str(o.kind)
            if "declined" in kind or "likely_to_accept" in kind:
                declined.append(
                    WidgetItem(
                        str(o.id),
                        o.title,
                        o.customer_name,
                        "open",
                        "high",
                        "/dashboard",
                        {"revenue": str(o.expected_revenue)},
                    )
                )

        approval_items: list[WidgetItem] = []
        advisor_queue = (sources.get("advisor") or {}).get("queue") or []
        for item in advisor_queue[:6]:
            kinds = item.get("kinds") or []
            if "approval_request" not in kinds and "repair_recommendation" not in kinds:
                continue
            approval_items.append(
                WidgetItem(
                    id=str(item.get("conversation_id") or item.get("customer_id") or len(approval_items)),
                    title=item.get("notes") or "Advisor suggestion",
                    subtitle=", ".join(kinds[:3]) or "advisor",
                    status="pending",
                    priority=str(item.get("priority") or "normal"),
                    href="/dashboard/ai-inbox",
                )
            )
        approvals = Widget(
            id="pending_approvals",
            title="Pending Approvals",
            items=approval_items,
        )

        repair_items: list[WidgetItem] = []
        # Walk-ins + appointments → Waiting / Active / Scheduled (time + status).
        crm = sources.get("crm") or {}
        appts = list((sources.get("scheduling") or {}).get("appointments") or [])
        appt_by_walk_in, appt_by_vehicle = _index_appointments_for_walk_ins(appts)
        linked_appt_ids: set[str] = set()

        for w in crm.get("open_walk_ins") or []:
            if not isinstance(w, dict):
                continue
            wid = str(w.get("id") or "")
            if not wid:
                continue
            vehicle = str(w.get("vehicle_label") or "Walk-in").strip() or "Walk-in"
            plate = str(w.get("license_plate") or "").strip()
            title = f"{vehicle}" + (f" · {plate}" if plate else "")
            complaint = str(w.get("complaint") or "").strip()
            arrived_raw = w.get("arrived_at")
            time_label = ""
            if isinstance(arrived_raw, str) and len(arrived_raw) >= 16:
                # ISO …THH:MM…
                time_label = arrived_raw[11:16]
            elif hasattr(arrived_raw, "strftime"):
                time_label = arrived_raw.strftime("%H:%M")

            linked = appt_by_walk_in.get(wid)
            if linked is None:
                vid = str(w.get("vehicle_id") or "")
                if vid:
                    linked = appt_by_vehicle.get(vid)
            column = _repair_column_status(linked, now=now)
            if linked is not None:
                aid = _appt_field(linked, "id")
                if aid:
                    linked_appt_ids.add(str(aid))
                start = _as_utc(_appt_field(linked, "start"))
                if start is not None:
                    time_label = start.strftime("%H:%M")

            subtitle_bits = [column, "walk-in"]
            if time_label:
                subtitle_bits.append(time_label)
            if complaint:
                subtitle_bits.append(complaint[:40])
            repair_items.append(
                WidgetItem(
                    wid,
                    title,
                    " · ".join(subtitle_bits),
                    column,
                    "high",
                    f"/dashboard/walk-ins/{wid}",
                )
            )

        for a in appts[:30]:
            aid = str(_appt_field(a, "id") or "")
            if aid and aid in linked_appt_ids:
                continue
            raw_status = str(_appt_field(a, "status") or "").lower()
            if raw_status in {"cancelled", "no_show", "completed"}:
                continue
            status = _repair_column_status(a, now=now)
            start = _as_utc(_appt_field(a, "start"))
            repair_type = str(_appt_field(a, "repair_type") or "general")
            priority = str(_appt_field(a, "priority") or "normal")
            repair_items.append(
                WidgetItem(
                    aid or repair_type,
                    repair_type.replace("_", " ").title(),
                    f"{status} · {start.strftime('%H:%M') if start else ''}",
                    status,
                    "high" if priority == "emergency" else "normal",
                    "/dashboard/appointments",
                )
            )

        return [
            tasks,
            Widget("customers_to_contact", "Customers To Contact", contact_items[:8]),
            Widget("declined_estimates", "Declined Estimates", declined[:8]),
            approvals,
            Widget("repair_status", "Repair Status", repair_items[:40]),
        ]


def _appt_field(appt: Any, name: str) -> Any:
    if appt is None:
        return None
    if isinstance(appt, dict):
        return appt.get(name)
    return getattr(appt, name, None)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _repair_column_status(appt: Any, *, now: datetime) -> str:
    """Map appointment (or none) → waiting | active | scheduled for Repair Status."""
    if appt is None:
        return "waiting"
    raw = str(_appt_field(appt, "status") or "").lower()
    if raw in {"cancelled", "no_show"}:
        return "waiting"
    if raw == "completed":
        return "scheduled"
    start = _as_utc(_appt_field(appt, "start"))
    end = _as_utc(_appt_field(appt, "end"))
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    if start is not None and now_utc < start:
        return "scheduled"
    # Slot ended — leave Active even if status is still in_progress / bay.
    if start is not None and end is not None and now_utc >= end:
        return "waiting"
    if "progress" in raw or raw == "active" or "bay" in raw:
        return "active"
    if start is not None and (end is None or now_utc < end):
        return "active"
    if raw in {"booked", "confirmed", "rescheduled"}:
        return "scheduled"
    return "waiting"


def _index_appointments_for_walk_ins(
    appts: list[Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_walk_in: dict[str, Any] = {}
    by_vehicle: dict[str, Any] = {}
    for a in appts:
        status = str(_appt_field(a, "status") or "").lower()
        if status in {"cancelled", "no_show", "completed"}:
            continue
        wid = _appt_field(a, "walk_in_id")
        if wid:
            by_walk_in.setdefault(str(wid), a)
        vid = _appt_field(a, "vehicle_id")
        if vid:
            by_vehicle.setdefault(str(vid), a)
    return by_walk_in, by_vehicle


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if hasattr(value, "snapshot") and callable(value.snapshot):
        return _safe(value.snapshot())
    # dataclasses / objects — keep shallow summary
    if hasattr(value, "open_opportunities"):
        return {
            "open_opportunities": value.open_opportunities,
            "expected_revenue_daily": str(getattr(value, "expected_revenue_daily", "")),
            "avg_customer_health": getattr(value, "avg_customer_health", None),
        }
    return str(type(value).__name__)
