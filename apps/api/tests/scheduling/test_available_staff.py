"""Tests that free staff is not rejected as unavailable."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.scheduling.agent_adapter import IntelligenceSchedulingStore
from app.scheduling.engines.availability import AvailabilityEngine, DEFAULT_SHOP_TZ
from app.scheduling.models import (
    Appointment,
    Bay,
    BookingRequest,
    BusinessHours,
    Mechanic,
    MechanicSkill,
)
from app.scheduling.service import AppointmentIntelligenceService
from app.scheduling.store import InMemoryShopResourceStore


def _open_hours() -> list[BusinessHours]:
    return [
        BusinessHours(weekday=d, open_time=time(8, 0), close_time=time(17, 0), closed=d >= 5)
        for d in range(7)
    ]


def _next_weekday_10am(avail: AvailabilityEngine, hours: list[BusinessHours]) -> datetime:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for offset in range(1, 12):
        day = (now + timedelta(days=offset)).date()
        window = avail.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=60) <= window[1]:
            return preferred
    raise AssertionError("no open weekday window")


@pytest.mark.asyncio
async def test_free_staff_takes_preferred_when_one_colleague_busy():
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    hours = _open_hours()
    store.set_business_hours(shop_id, hours)
    busy = Mechanic(
        id=uuid4(),
        shop_id=shop_id,
        name="Busy",
        skills=[MechanicSkill("oil_change", 5)],
        hourly_rate=Decimal("70"),
    )
    free = Mechanic(
        id=uuid4(),
        shop_id=shop_id,
        name="Free",
        skills=[MechanicSkill("oil_change", 4)],
        hourly_rate=Decimal("70"),
    )
    store.set_mechanics(shop_id, [busy, free])
    bays = [
        Bay(id=uuid4(), shop_id=shop_id, name="Bay 1", bay_type="general"),
        Bay(id=uuid4(), shop_id=shop_id, name="Bay 2", bay_type="general"),
    ]
    store.set_bays(shop_id, bays)
    intel = AppointmentIntelligenceService(store=store)
    preferred = _next_weekday_10am(intel._availability, hours)
    await store.save_appointment(
        Appointment(
            id=uuid4(),
            shop_id=shop_id,
            start=preferred,
            end=preferred + timedelta(minutes=30),
            status="booked",
            repair_type="oil_change",
            mechanic_id=busy.id,
            bay_id=bays[0].id,
            estimated_duration_min=30,
        )
    )
    result = await intel.book(
        BookingRequest(
            shop_id=shop_id,
            preferred_start=preferred,
            repair_type="oil_change",
            estimated_duration_min=30,
        )
    )
    assert result.success, result.message
    assert result.appointment is not None
    assert result.appointment.mechanic_id == free.id
    assert result.appointment.start == preferred


@pytest.mark.asyncio
async def test_string_workdays_still_count_as_available():
    """JSON / loose clients may store workdays as strings — must not false-busy."""
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    hours = _open_hours()
    store.set_business_hours(shop_id, hours)
    tech = Mechanic(
        id=uuid4(),
        shop_id=shop_id,
        name="Tech",
        skills=[MechanicSkill("oil_change", 5)],
        workdays=["0", "1", "2", "3", "4"],  # type: ignore[list-item]
        hourly_rate=Decimal("70"),
    )
    store.set_mechanics(shop_id, [tech])
    store.set_bays(
        shop_id, [Bay(id=uuid4(), shop_id=shop_id, name="Bay 1", bay_type="general")]
    )
    intel = AppointmentIntelligenceService(store=store)
    preferred = _next_weekday_10am(intel._availability, hours)
    result = await intel.book(
        BookingRequest(
            shop_id=shop_id,
            preferred_start=preferred,
            repair_type="oil_change",
            estimated_duration_min=30,
        )
    )
    assert result.success, result.message


@pytest.mark.asyncio
async def test_reschedule_probe_excludes_own_appointment():
    """Same-time move (or service swap keep-time) must not reject itself."""
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    hours = _open_hours()
    store.set_business_hours(shop_id, hours)
    tech = Mechanic(
        id=uuid4(),
        shop_id=shop_id,
        name="Solo",
        skills=[MechanicSkill("oil_change", 5)],
        hourly_rate=Decimal("70"),
    )
    bay = Bay(id=uuid4(), shop_id=shop_id, name="Bay 1", bay_type="general")
    store.set_mechanics(shop_id, [tech])
    store.set_bays(shop_id, [bay])
    intel = AppointmentIntelligenceService(store=store)
    adapter = IntelligenceSchedulingStore(intel)
    preferred = _next_weekday_10am(intel._availability, hours)
    appt_id = uuid4()
    await store.save_appointment(
        Appointment(
            id=appt_id,
            shop_id=shop_id,
            start=preferred,
            end=preferred + timedelta(minutes=30),
            status="booked",
            repair_type="oil_change",
            mechanic_id=tech.id,
            bay_id=bay.id,
            estimated_duration_min=30,
        )
    )
    blocked = await adapter.probe_slot_at(
        shop_id,
        preferred_start=preferred,
        duration_minutes=30,
        repair_type="oil_change",
    )
    assert blocked is None
    free = await adapter.probe_slot_at(
        shop_id,
        preferred_start=preferred,
        duration_minutes=30,
        repair_type="oil_change",
        exclude_appointment_id=appt_id,
    )
    assert free is not None
    assert free.start == preferred


@pytest.mark.asyncio
async def test_completed_appointment_does_not_block_staff():
    shop_id = uuid4()
    store = InMemoryShopResourceStore()
    hours = _open_hours()
    store.set_business_hours(shop_id, hours)
    tech = Mechanic(
        id=uuid4(),
        shop_id=shop_id,
        name="Tech",
        skills=[MechanicSkill("oil_change", 5)],
        hourly_rate=Decimal("70"),
    )
    bay = Bay(id=uuid4(), shop_id=shop_id, name="Bay 1", bay_type="general")
    store.set_mechanics(shop_id, [tech])
    store.set_bays(shop_id, [bay])
    intel = AppointmentIntelligenceService(store=store)
    preferred = _next_weekday_10am(intel._availability, hours)
    await store.save_appointment(
        Appointment(
            id=uuid4(),
            shop_id=shop_id,
            start=preferred,
            end=preferred + timedelta(minutes=30),
            status="completed",
            repair_type="oil_change",
            mechanic_id=tech.id,
            bay_id=bay.id,
            estimated_duration_min=30,
        )
    )
    result = await intel.book(
        BookingRequest(
            shop_id=shop_id,
            preferred_start=preferred,
            repair_type="oil_change",
            estimated_duration_min=30,
        )
    )
    assert result.success, result.message
