"""Phase 13 Executive Dashboard tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.executive.factory import (
    build_executive_runtime,
    reset_executive_runtime,
)
from app.executive.store import InMemoryExecutiveStore
from app.scheduling.factory import build_scheduling_runtime, reset_scheduling_runtime
from app.scheduling.store import InMemoryShopResourceStore


@pytest.fixture(autouse=True)
def _reset():
    reset_executive_runtime()
    reset_scheduling_runtime()
    yield
    reset_executive_runtime()
    reset_scheduling_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    # Seed scheduling shop so aggregator can list appointments
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)
    build_scheduling_runtime(store=store)
    return build_executive_runtime(store=InMemoryExecutiveStore())


@pytest.mark.asyncio
async def test_dashboard_has_required_cards(runtime, shop_id):
    snap = await runtime.service.get_dashboard(shop_id, force=True)
    ids = {c.id for c in snap.cards}
    required = {
        "todays_revenue",
        "expected_revenue",
        "appointments",
        "missed_calls",
        "walk_ins",
        "ai_conversations",
        "human_escalations",
        "revenue_opportunities",
        "marketing_roi",
        "customer_satisfaction",
        "mechanic_productivity",
    }
    assert required.issubset(ids)


@pytest.mark.asyncio
async def test_dashboard_has_required_charts(runtime, shop_id):
    snap = await runtime.service.get_dashboard(shop_id, force=True)
    ids = {c.id for c in snap.charts}
    required = {
        "revenue",
        "appointments",
        "retention",
        "vehicle_types",
        "services",
        "customer_sources",
        "ai_performance",
    }
    assert required.issubset(ids)


@pytest.mark.asyncio
async def test_dashboard_has_required_widgets(runtime, shop_id):
    snap = await runtime.service.get_dashboard(shop_id, force=True)
    ids = {w.id for w in snap.widgets}
    required = {
        "todays_tasks",
        "customers_to_contact",
        "declined_estimates",
        "pending_approvals",
        "repair_status",
    }
    assert required.issubset(ids)


@pytest.mark.asyncio
async def test_empty_shop_has_zero_metrics(runtime, shop_id):
    snap = await runtime.service.get_dashboard(shop_id, force=True)
    assert snap.live["todays_revenue"] in {"0", "0.00", "0.0"}
    assert snap.live["expected_revenue"] in {"0", "0.00", "0.0"}
    assert snap.live["appointments_today"] == 0
    assert snap.live["revenue_opportunities"] == 0
    assert snap.live["ai_conversations"] == 0
    by_id = {w.id: w for w in snap.widgets}
    assert by_id["customers_to_contact"].items == []
    assert by_id["declined_estimates"].items == []
    assert by_id["repair_status"].items == []
    assert by_id["todays_tasks"].items == []


@pytest.mark.asyncio
async def test_realtime_cache_and_version_bump(runtime, shop_id):
    a = await runtime.service.get_dashboard(shop_id, force=True)
    b = await runtime.service.get_dashboard(shop_id, force=False, max_age_seconds=60)
    assert a.version == b.version
    assert a.generated_at == b.generated_at

    c = await runtime.service.bump_live(shop_id, walk_ins_today=9)
    assert c.version > a.version
    # CRM SQL counts overwrite in-memory bumps on refresh (empty shop → 0).
    assert c.live["walk_ins_today"] == 0


def test_apply_sources_wires_crm_new_customers(runtime, shop_id):
    from app.executive.models import ShopLiveState

    live = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live,
        {"crm": {"customers_today": 4, "walk_ins_today": 1, "customers_total": 4}},
    )
    assert live.walk_ins_today == 4
    assert live.customers_total == 4

    live2 = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live2,
        {"crm": {"customers_today": 0, "walk_ins_today": 3, "customers_total": 0}},
    )
    assert live2.walk_ins_today == 3
    assert live2.customers_total == 0


def test_apply_sources_follow_up_customers_from_marketing(runtime, shop_id):
    """Follow-up Customers KPI prefers marketing audiences over revenue opps."""
    from types import SimpleNamespace

    from app.executive.models import ShopLiveState

    live = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live,
        {
            "revenue": {
                "dashboard": SimpleNamespace(
                    expected_revenue_daily=0,
                    open_opportunities=99,
                    avg_customer_health=0,
                )
            },
            "marketing": {"summary": {}, "follow_up_customers": 7},
        },
    )
    assert live.revenue_opportunities == 7

    # Fall back to revenue open opportunities when marketing count missing.
    live2 = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live2,
        {
            "revenue": {
                "dashboard": SimpleNamespace(
                    expected_revenue_daily=0,
                    open_opportunities=12,
                    avg_customer_health=0,
                )
            },
            "marketing": {"summary": {}},
        },
    )
    assert live2.revenue_opportunities == 12

    # Marketing error should not wipe with a bogus zero follow_up field alone —
    # prefer revenue fallback when error is set.
    live3 = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live3,
        {
            "revenue": {
                "dashboard": SimpleNamespace(
                    expected_revenue_daily=0,
                    open_opportunities=5,
                    avg_customer_health=0,
                )
            },
            "marketing": {"error": "boom", "follow_up_customers": 0},
        },
    )
    assert live3.revenue_opportunities == 5


def test_apply_sources_todays_revenue_from_completed_work(runtime, shop_id):
    from decimal import Decimal
    from types import SimpleNamespace

    from app.executive.models import ShopLiveState

    live = ShopLiveState(shop_id=shop_id, todays_revenue=Decimal("999.00"))
    runtime.aggregator._apply_sources(
        live,
        {
            "scheduling": {
                "appointments_today": 3,
                "expected_daily_revenue": "450.00",
                "completed_revenue_today": "275.50",
            },
            "revenue": {},
            "marketing": {"summary": {"revenue": "1000"}},
        },
    )
    assert live.todays_revenue == Decimal("275.50")
    assert live.expected_revenue == Decimal("450.00")

    # Fallback: sum completed appointments when aggregate field missing.
    live2 = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live2,
        {
            "scheduling": {
                "appointments": [
                    SimpleNamespace(status="completed", estimated_revenue=Decimal("120.00")),
                    SimpleNamespace(status="booked", estimated_revenue=Decimal("200.00")),
                    SimpleNamespace(status="completed", estimated_revenue=Decimal("80.25")),
                    SimpleNamespace(status="cancelled", estimated_revenue=Decimal("50.00")),
                ]
            }
        },
    )
    assert live2.todays_revenue == Decimal("200.25")

    # Cold scheduling source clears stale revenue.
    live3 = ShopLiveState(shop_id=shop_id, todays_revenue=Decimal("50.00"))
    runtime.aggregator._apply_sources(live3, {"scheduling": {"appointments_today": 0}})
    assert live3.todays_revenue == Decimal("0")


def test_repair_status_includes_open_walk_ins(runtime, shop_id):
    from datetime import datetime, timezone

    from app.executive.models import ShopLiveState

    visit_id = str(uuid4())
    live = ShopLiveState(shop_id=shop_id)
    widgets = runtime.aggregator._build_widgets(
        live,
        {
            "crm": {
                "open_walk_ins": [
                    {
                        "id": visit_id,
                        "complaint": "Brake noise",
                        "status": "converted",
                        "arrived_at": datetime(2026, 8, 2, 15, 30, tzinfo=timezone.utc).isoformat(),
                        "vehicle_label": "2019 Honda Civic",
                        "license_plate": "ABC123",
                    }
                ]
            },
            "scheduling": {"appointments": []},
            "revenue": {},
            "advisor": {},
        },
        now=datetime.now(timezone.utc),
    )
    by_id = {w.id: w for w in widgets}
    items = by_id["repair_status"].items
    assert len(items) == 1
    assert items[0].id == visit_id
    assert items[0].status == "waiting"
    assert "Honda Civic" in items[0].title
    assert items[0].href == f"/dashboard/walk-ins/{visit_id}"
    assert "waiting" in items[0].subtitle


def test_repair_status_walk_in_follows_linked_appointment(runtime, shop_id):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.executive.models import ShopLiveState

    now = datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc)
    waiting_id = str(uuid4())
    active_id = str(uuid4())
    scheduled_id = str(uuid4())
    vehicle_id = str(uuid4())
    active_appt_id = uuid4()
    scheduled_appt_id = uuid4()

    live = ShopLiveState(shop_id=shop_id)
    widgets = runtime.aggregator._build_widgets(
        live,
        {
            "crm": {
                "open_walk_ins": [
                    {
                        "id": waiting_id,
                        "complaint": "No appt yet",
                        "status": "open",
                        "arrived_at": now.isoformat(),
                        "vehicle_label": "2018 Toyota Corolla",
                        "license_plate": "WAIT1",
                    },
                    {
                        "id": active_id,
                        "complaint": "In bay",
                        "status": "converted",
                        "arrived_at": (now - timedelta(hours=1)).isoformat(),
                        "vehicle_id": vehicle_id,
                        "vehicle_label": "2020 Ford F-150",
                        "license_plate": "ACT1",
                    },
                    {
                        "id": scheduled_id,
                        "complaint": "Booked later",
                        "status": "open",
                        "arrived_at": now.isoformat(),
                        "vehicle_label": "2021 Tesla Model 3",
                        "license_plate": "SCH1",
                    },
                ]
            },
            "scheduling": {
                "appointments": [
                    SimpleNamespace(
                        id=active_appt_id,
                        walk_in_id=None,
                        vehicle_id=vehicle_id,
                        status="booked",
                        start=now - timedelta(minutes=30),
                        end=now + timedelta(minutes=30),
                        repair_type="brakes",
                        priority="normal",
                    ),
                    SimpleNamespace(
                        id=scheduled_appt_id,
                        walk_in_id=scheduled_id,
                        vehicle_id=None,
                        status="booked",
                        start=now + timedelta(hours=2),
                        end=now + timedelta(hours=3),
                        repair_type="oil_change",
                        priority="normal",
                    ),
                ]
            },
            "revenue": {},
            "advisor": {},
        },
        now=now,
    )
    by_id = {w.id: w for w in widgets}
    items = {i.id: i for i in by_id["repair_status"].items}

    assert items[waiting_id].status == "waiting"
    assert items[active_id].status == "active"
    assert items[scheduled_id].status == "scheduled"
    # Linked appointments are represented by the walk-in row only.
    assert str(active_appt_id) not in items
    assert str(scheduled_appt_id) not in items
    assert "active" in (items[active_id].subtitle or "")
    assert "scheduled" in (items[scheduled_id].subtitle or "")
    # Active stays on visit detail; scheduled deep-links to the day board.
    assert items[active_id].href == f"/dashboard/walk-ins/{active_id}"
    assert items[scheduled_id].href == (
        f"/dashboard/appointments?date=2026-08-02&appointment={scheduled_appt_id}"
    )


def test_repair_status_leaves_active_after_appointment_end(runtime, shop_id):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.executive.models import ShopLiveState

    # Appointment slot 08:00–09:00; now is past end.
    now = datetime(2026, 8, 2, 9, 5, tzinfo=timezone.utc)
    visit_id = str(uuid4())
    appt_id = uuid4()
    vehicle_id = str(uuid4())

    live = ShopLiveState(shop_id=shop_id)
    widgets = runtime.aggregator._build_widgets(
        live,
        {
            "crm": {
                "open_walk_ins": [
                    {
                        "id": visit_id,
                        "complaint": "Oil change",
                        "status": "converted",
                        "arrived_at": (now - timedelta(hours=1)).isoformat(),
                        "vehicle_id": vehicle_id,
                        "vehicle_label": "2019 Honda Civic",
                        "license_plate": "END1",
                    }
                ]
            },
            "scheduling": {
                "appointments": [
                    SimpleNamespace(
                        id=appt_id,
                        walk_in_id=None,
                        vehicle_id=vehicle_id,
                        status="in_progress",
                        start=now - timedelta(hours=1, minutes=5),
                        end=now - timedelta(minutes=5),
                        repair_type="oil_change",
                        priority="normal",
                    ),
                ]
            },
            "revenue": {},
            "advisor": {},
        },
        now=now,
    )
    by_id = {w.id: w for w in widgets}
    items = {i.id: i for i in by_id["repair_status"].items}

    assert items[visit_id].status == "waiting"
    assert "waiting" in (items[visit_id].subtitle or "")


def test_repair_status_appointment_deep_links_to_schedule_day(runtime, shop_id):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.executive.models import ShopLiveState

    now = datetime(2026, 8, 2, 16, 0, tzinfo=timezone.utc)
    appt_id = uuid4()
    live = ShopLiveState(shop_id=shop_id)
    widgets = runtime.aggregator._build_widgets(
        live,
        {
            "crm": {"open_walk_ins": []},
            "scheduling": {
                "appointments": [
                    SimpleNamespace(
                        id=appt_id,
                        walk_in_id=None,
                        vehicle_id=None,
                        status="booked",
                        start=now + timedelta(hours=3),
                        end=now + timedelta(hours=4),
                        repair_type="tire_rotation",
                        priority="normal",
                    ),
                ]
            },
            "revenue": {},
            "advisor": {},
        },
        now=now,
    )
    by_id = {w.id: w for w in widgets}
    items = {i.id: i for i in by_id["repair_status"].items}
    assert str(appt_id) in items
    assert items[str(appt_id)].status == "scheduled"
    assert items[str(appt_id)].href == (
        f"/dashboard/appointments?date=2026-08-02&appointment={appt_id}"
    )


def test_ai_performance_appts_booked_uses_scheduling_created_count(runtime, shop_id):
    from datetime import datetime, timezone

    from app.executive.models import ShopLiveState

    now = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)
    live = ShopLiveState(shop_id=shop_id, appointments_today=5, human_escalations=0)
    charts = runtime.aggregator._build_charts(
        live,
        {
            "scheduling": {"ai_appointments_created_today": 3, "appointments_today": 5},
            "sms": {"monitor": {"appointments_booked": 99, "inbound_received": 2}},
            "voice": {"monitor": {"turns": 1}},
            "revenue": {},
        },
        now=now,
    )
    by_id = {c.id: c for c in charts}
    points = {p.label: p.value for p in by_id["ai_performance"].points}
    assert points["Appts booked"] == 3.0


def test_ai_conversations_prefer_durable_voice_calls(runtime, shop_id):
    from datetime import datetime, timezone

    from app.executive.models import ShopLiveState

    live = ShopLiveState(shop_id=shop_id)
    runtime.aggregator._apply_sources(
        live,
        {
            "sms": {"monitor": {"inbound_received": 4, "escalations": 1}},
            "voice": {"monitor": {"calls_started": 7, "turns": 40, "escalations": 0}},
        },
    )
    assert live.ai_conversations == 11  # inbound SMS + voice calls (not turns)
    assert live.human_escalations == 1

    charts = runtime.aggregator._build_charts(
        live,
        {
            "sms": {"monitor": {"inbound_received": 4}},
            "voice": {"monitor": {"calls_started": 7, "turns": 40}},
            "scheduling": {},
            "revenue": {},
        },
        now=datetime.now(timezone.utc),
    )
    points = {p.label: p.value for p in next(c for c in charts if c.id == "ai_performance").points}
    assert points["SMS handled"] == 4.0
    assert points["Voice turns"] == 7.0


def test_ai_appointment_created_helpers():
    from datetime import datetime, timezone

    from app.plugins.scheduling.plugin import (
        _created_in_day_bounds,
        _is_ai_appointment_source,
    )

    assert _is_ai_appointment_source("agent")
    assert _is_ai_appointment_source("sms")
    assert _is_ai_appointment_source("phone")
    assert not _is_ai_appointment_source("dashboard")
    assert not _is_ai_appointment_source("walk_in")

    day_start = datetime(2026, 8, 11, 7, 0, tzinfo=timezone.utc)  # midnight LA PDT
    day_end = datetime(2026, 8, 12, 7, 0, tzinfo=timezone.utc)
    assert _created_in_day_bounds(
        datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
        day_start=day_start,
        day_end=day_end,
    )
    assert not _created_in_day_bounds(
        datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc),
        day_start=day_start,
        day_end=day_end,
    )


@pytest.mark.asyncio
async def test_main_imports_executive_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/executive/dashboard" in paths
    assert "/v1/executive/stream" in paths
