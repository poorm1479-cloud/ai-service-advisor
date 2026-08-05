"""Unit tests for Team/catalog → scheduling resource sync."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.scheduling.catalog import (
    _stable_bay_id,
    sync_catalog_bays,
    sync_catalog_hours,
    sync_team_mechanics,
)
from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import Appointment, Mechanic, MechanicSkill
from app.scheduling.store import InMemoryShopResourceStore
from app.shop_setup.schemas import BusinessHoursOut, ServiceOut


def _service(
    *,
    bay: str,
    skill: str = "general",
    name: str = "Svc",
    shop_id: object | None = None,
) -> ServiceOut:
    return ServiceOut(
        id=uuid4(),
        shop_id=shop_id or uuid4(),
        name=name,
        category="maintenance",
        duration_minutes=60,
        price=Decimal("99.00"),
        skill=skill,
        bay=bay,
        active=True,
        sort_order=0,
    )


@pytest.mark.asyncio
async def test_sync_catalog_bays_one_lane_per_team_member(monkeypatch):
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)
    store.set_mechanics(
        shop_id,
        [
            Mechanic(
                id=uuid4(),
                shop_id=shop_id,
                name=f"Tech {i}",
                skills=[MechanicSkill("general", 4)],
            )
            for i in range(3)
        ],
    )

    services = [
        _service(bay="quick_service", skill="oil_change", name="Oil"),
        _service(bay="general", skill="brakes", name="Brakes"),
        _service(bay="quick_service", skill="oil_change", name="Oil Plus"),
    ]

    class FakeSetup:
        def __init__(self, _session):
            pass

        async def list_services(self, _shop_id, *, active_only=False):
            return services

    monkeypatch.setattr("app.scheduling.catalog.ShopSetupService", FakeSetup)

    await sync_catalog_bays(session=SimpleNamespace(), shop_id=shop_id, store=store)
    bays = await store.list_bays(shop_id)
    assert len(bays) == 3
    assert {b.id for b in bays} == {_stable_bay_id(shop_id, "lane", i) for i in range(3)}
    assert [b.name for b in bays] == ["Bay 1", "Bay 2", "Bay 3"]
    # Labels rotate across catalog types for preference scoring only.
    assert sorted(b.bay_type for b in bays) == ["general", "quick_service", "quick_service"]


@pytest.mark.asyncio
async def test_sync_team_mechanics_uses_entire_active_roster(monkeypatch):
    shop_id = uuid4()
    owner_id = uuid4()
    tech_id = uuid4()
    desk_id = uuid4()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)

    owner = SimpleNamespace(id=owner_id, full_name="Owner Kim", is_active=True)
    tech = SimpleNamespace(id=tech_id, full_name="Tech Lee", is_active=True)
    desk = SimpleNamespace(id=desk_id, full_name="Desk Park", is_active=True)

    rows = [
        (
            SimpleNamespace(role="owner", created_at=None),
            owner,
        ),
        (
            SimpleNamespace(role="staff", created_at=None),
            tech,
        ),
        (
            SimpleNamespace(role="staff", created_at=None),
            desk,
        ),
    ]

    class FakeResult:
        def all(self):
            return rows

    class FakeSession:
        async def execute(self, _stmt):
            return FakeResult()

    class FakeSetup:
        def __init__(self, _session):
            pass

        async def list_services(self, _shop_id, *, active_only=False):
            return [
                _service(bay="general", skill="brakes"),
                _service(bay="quick_service", skill="oil_change"),
            ]

    monkeypatch.setattr("app.scheduling.catalog.ShopSetupService", FakeSetup)

    await sync_team_mechanics(session=FakeSession(), shop_id=shop_id, store=store)
    mechanics = await store.list_mechanics(shop_id)
    names = sorted(m.name for m in mechanics)
    assert names == ["Desk Park", "Owner Kim", "Tech Lee"]
    skills = {s.repair_type for s in mechanics[0].skills}
    assert skills == {"brakes", "oil_change"}
    by_name = {m.name: m.role for m in mechanics}
    assert by_name["Owner Kim"] == "owner"
    assert by_name["Tech Lee"] == "staff"
    assert by_name["Desk Park"] == "staff"


@pytest.mark.asyncio
async def test_sync_catalog_hours_applies_settings_window(monkeypatch):
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)

    hours_out = [
        BusinessHoursOut(
            weekday=d,
            open_time="09:30" if d < 5 else "10:00",
            close_time="18:30" if d < 5 else "14:00",
            closed=d >= 6,
        )
        for d in range(7)
    ]

    class FakeSetup:
        def __init__(self, _session):
            pass

        async def get_state(self, _shop_id):
            return SimpleNamespace(business_hours=hours_out)

    monkeypatch.setattr("app.scheduling.catalog.ShopSetupService", FakeSetup)

    workdays, work_start, work_end = await sync_catalog_hours(
        session=SimpleNamespace(), shop_id=shop_id, store=store
    )
    assert workdays == [0, 1, 2, 3, 4, 5]
    assert work_start == time(9, 30)
    assert work_end == time(18, 30)

    stored = await store.list_business_hours(shop_id)
    monday = next(h for h in stored if h.weekday == 0)
    assert monday.open_time == time(9, 30)
    assert monday.close_time == time(18, 30)
    assert next(h for h in stored if h.weekday == 6).closed is True


@pytest.mark.asyncio
async def test_sync_team_mechanics_uses_settings_work_window(monkeypatch):
    shop_id = uuid4()
    tech_id = uuid4()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)

    class FakeResult:
        def all(self):
            return [
                (
                    SimpleNamespace(role="staff", created_at=None),
                    SimpleNamespace(id=tech_id, full_name="Tech Lee", is_active=True),
                )
            ]

    class FakeSession:
        async def execute(self, _stmt):
            return FakeResult()

    class FakeSetup:
        def __init__(self, _session):
            pass

        async def list_services(self, _shop_id, *, active_only=False):
            return [_service(bay="general", skill="general")]

    monkeypatch.setattr("app.scheduling.catalog.ShopSetupService", FakeSetup)

    await sync_team_mechanics(
        session=FakeSession(),
        shop_id=shop_id,
        store=store,
        workdays=[0, 1, 2, 3, 4, 5],
        work_start=time(9, 30),
        work_end=time(18, 30),
    )
    mechanics = await store.list_mechanics(shop_id)
    assert len(mechanics) == 1
    assert mechanics[0].work_start == time(9, 30)
    assert mechanics[0].work_end == time(18, 30)
    assert mechanics[0].workdays == [0, 1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_sync_team_mechanics_remaps_seed_appointment_assignee(monkeypatch):
    """SMS may book against seed mechanics before Schedule syncs Team."""
    shop_id = uuid4()
    tech_id = uuid4()
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)
    seed = (await store.list_mechanics(shop_id))[0]
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    await store.save_appointment(
        Appointment(
            id=uuid4(),
            shop_id=shop_id,
            start=start,
            end=start + timedelta(hours=1),
            status=AppointmentStatus.BOOKED.value,
            mechanic_id=seed.id,
            source="agent",
            notes="sms oil change",
        )
    )

    class FakeResult:
        def all(self):
            return [
                (
                    SimpleNamespace(role="staff", created_at=None),
                    SimpleNamespace(id=tech_id, full_name="Tech Lee", is_active=True),
                )
            ]

    class FakeSession:
        async def execute(self, _stmt):
            return FakeResult()

    class FakeSetup:
        def __init__(self, _session):
            pass

        async def list_services(self, _shop_id, *, active_only=False):
            return [_service(bay="general", skill="general")]

    monkeypatch.setattr("app.scheduling.catalog.ShopSetupService", FakeSetup)

    await sync_team_mechanics(session=FakeSession(), shop_id=shop_id, store=store)
    appts = await store.list_appointments(shop_id)
    assert len(appts) == 1
    assert appts[0].mechanic_id == tech_id
