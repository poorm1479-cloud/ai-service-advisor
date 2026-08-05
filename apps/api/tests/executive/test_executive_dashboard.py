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


@pytest.mark.asyncio
async def test_main_imports_executive_routes():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/v1/executive/dashboard" in paths
    assert "/v1/executive/stream" in paths
