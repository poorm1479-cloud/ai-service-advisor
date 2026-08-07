"""Appointment intelligence unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.scheduling.factory import build_scheduling_runtime, reset_scheduling_runtime
from app.scheduling.models import Bay, BookingRequest
from app.scheduling.store import InMemoryShopResourceStore


@pytest.fixture(autouse=True)
def _reset():
    reset_scheduling_runtime()
    yield
    reset_scheduling_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime(shop_id):
    store = InMemoryShopResourceStore()
    store.ensure_shop(shop_id)
    return build_scheduling_runtime(store=store)


@pytest.mark.asyncio
async def test_book_assigns_mechanic_and_bay(runtime, shop_id):
    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="brakes",
            vehicle_type="sedan",
            priority="normal",
        )
    )
    assert result.success
    assert result.appointment is not None
    assert result.appointment.mechanic_id is not None
    assert result.appointment.bay_id is not None
    assert result.appointment.estimated_duration_min > 0
    assert result.appointment.estimated_completion is not None
    assert result.ai_decisions["mechanic_name"]
    assert result.ai_decisions["bay_name"]


@pytest.mark.asyncio
async def test_book_honors_exact_preferred_start(runtime, shop_id):
    """Preferred start must book at that time, not a nearby optimized slot."""
    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=60) <= window[1]:
            break
    assert preferred is not None

    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="oil_change",
            vehicle_type="sedan",
            priority="normal",
            preferred_start=preferred,
            estimated_duration_min=30,
        )
    )
    assert result.success
    assert result.appointment is not None
    assert result.appointment.start == preferred
    assert result.appointment.end == preferred + timedelta(minutes=30)


@pytest.mark.asyncio
async def test_book_rejects_unavailable_preferred_start(runtime, shop_id):
    first = await runtime.service.book(
        BookingRequest(shop_id=shop_id, repair_type="diagnostic", priority="high")
    )
    assert first.success and first.appointment

    second = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="diagnostic",
            preferred_start=first.appointment.start,
            mechanic_id=first.appointment.mechanic_id,
            bay_id=first.appointment.bay_id,
            estimated_duration_min=first.appointment.estimated_duration_min,
        )
    )
    assert not second.success
    assert second.conflicts and second.conflicts.has_conflict
    assert "not available" in (second.message or "").lower() or "unavailable" in (
        second.message or ""
    ).lower()


@pytest.mark.asyncio
async def test_emergency_prefers_earlier_slot(runtime, shop_id):
    normal = await runtime.service.recommend_slots(
        BookingRequest(shop_id=shop_id, repair_type="oil_change", priority="normal"),
        limit=5,
    )
    emergency = await runtime.service.recommend_slots(
        BookingRequest(shop_id=shop_id, repair_type="oil_change", priority="emergency"),
        limit=5,
    )
    assert emergency
    assert normal
    assert emergency[0].start <= normal[0].start + timedelta(hours=8)


@pytest.mark.asyncio
async def test_conflict_detection_on_double_book(runtime, shop_id):
    first = await runtime.service.book(
        BookingRequest(shop_id=shop_id, repair_type="diagnostic", priority="high")
    )
    assert first.success and first.appointment
    # Force same mechanic/bay/time via second book with same preferred start
    second = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="diagnostic",
            preferred_start=first.appointment.start,
            mechanic_id=first.appointment.mechanic_id,
            bay_id=first.appointment.bay_id,
            estimated_duration_min=first.appointment.estimated_duration_min,
        )
    )
    # Optimizer should pick an alternative free slot (success) or report conflict
    assert second.success or (second.conflicts and second.conflicts.has_conflict)


@pytest.mark.asyncio
async def test_reschedule_and_cancel(runtime, shop_id):
    booked = await runtime.service.book(
        BookingRequest(shop_id=shop_id, repair_type="tires")
    )
    assert booked.appointment
    hours = await runtime.service._store.list_business_hours(shop_id)
    # Prefer next open calendar day (not +1 which may land on a closed weekend).
    new_start = None
    base = booked.appointment.start
    for offset in range(1, 8):
        candidate = base + timedelta(days=offset)
        window = runtime.service._availability.day_window(
            hours, runtime.service._availability.local_date(candidate)
        )
        if window is None:
            continue
        local = candidate.astimezone(runtime.service._availability._shop_tz)
        new_start = local.replace(
            hour=max(10, window[0].astimezone(runtime.service._availability._shop_tz).hour),
            minute=0,
            second=0,
            microsecond=0,
        )
        if new_start < window[0]:
            new_start = window[0]
        if new_start + timedelta(minutes=60) <= window[1]:
            break
        new_start = None
    assert new_start is not None
    moved = await runtime.service.reschedule(
        shop_id=shop_id,
        appointment_id=booked.appointment.id,
        preferred_start=new_start,
    )
    assert moved.success
    assert moved.appointment is not None
    cancelled = await runtime.service.cancel(
        shop_id=shop_id, appointment_id=moved.appointment.id, reason="customer"
    )
    assert cancelled is not None
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_capacity_forecast_and_optimize(runtime, shop_id):
    for _ in range(3):
        await runtime.service.book(
            BookingRequest(shop_id=shop_id, repair_type="oil_change")
        )
    day = datetime.now(timezone.utc).date()
    # May be weekend — book may land on next weekday
    appts = await runtime.service.list_appointments(shop_id)
    assert appts
    day = appts[0].start.date()
    forecast = await runtime.service.capacity_forecast(shop_id, day)
    assert forecast.booked_minutes > 0
    assert forecast.expected_revenue > 0
    optimized = await runtime.service.optimize_schedule(shop_id, day)
    assert optimized.expected_daily_revenue > 0
    assert isinstance(optimized.mechanic_utilization, dict)
    assert isinstance(optimized.improvements, list)


@pytest.mark.asyncio
async def test_agent_adapter_book(runtime, shop_id):
    slots = await runtime.agent_store.list_available_slots(shop_id, days_ahead=5)
    assert slots
    record = await runtime.agent_store.book(
        shop_id,
        start=slots[0].start,
        end=slots[0].end,
        customer_id=uuid4(),
        vehicle_id=None,
        notes="via agent",
    )
    assert record.status == "booked"
    assert record.start == slots[0].start or record.start >= slots[0].start


@pytest.mark.asyncio
async def test_agent_adapter_lists_slots_for_catalog_skill(runtime, shop_id):
    """Team synced without a literal 'general' skill must still surface openings."""
    from decimal import Decimal

    from app.scheduling.models import Mechanic, MechanicSkill

    store = runtime.service._store  # noqa: SLF001
    store.set_mechanics(
        shop_id,
        [
            Mechanic(
                id=uuid4(),
                shop_id=shop_id,
                name="Oil Only",
                skills=[MechanicSkill("oil_change", 5, 30)],
                hourly_rate=Decimal("70"),
            )
        ],
    )
    # Free staff without a "general" tag still count as capacity (soft skill).
    general_slots = await runtime.service.recommend_slots(
        BookingRequest(shop_id=shop_id, repair_type="general", estimated_duration_min=30),
        days_ahead=5,
        limit=10,
    )
    assert general_slots
    slots = await runtime.agent_store.list_available_slots(
        shop_id, days_ahead=5, duration_minutes=30, repair_type="oil_change"
    )
    assert slots
    fallback = await runtime.agent_store.list_available_slots(
        shop_id, days_ahead=5, duration_minutes=30
    )
    assert fallback


@pytest.mark.asyncio
async def test_probe_and_book_when_staff_free_without_skill_tags(runtime, shop_id):
    """Free Team member without catalog skill tags must still take preferred clock."""
    from decimal import Decimal

    from app.scheduling.models import Mechanic

    store = runtime.service._store  # noqa: SLF001
    store.set_mechanics(
        shop_id,
        [
            Mechanic(
                id=uuid4(),
                shop_id=shop_id,
                name="Untagged Tech",
                skills=[],  # common after Team sync without skill matrix
                hourly_rate=Decimal("70"),
            )
        ],
    )
    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=60) <= window[1]:
            break
    assert preferred is not None

    probed = await runtime.agent_store.probe_slot_at(
        shop_id,
        preferred_start=preferred,
        duration_minutes=30,
        repair_type="oil_change",
    )
    assert probed is not None
    assert probed.start == preferred

    book = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="oil_change",
            preferred_start=preferred,
            estimated_duration_min=30,
        )
    )
    assert book.success
    assert book.appointment is not None
    assert book.appointment.start == preferred


@pytest.mark.asyncio
async def test_skill_based_mechanic_for_engine(runtime, shop_id):
    result = await runtime.service.book(
        BookingRequest(shop_id=shop_id, repair_type="engine", vehicle_type="sedan")
    )
    assert result.success
    mechanics = await runtime.service.list_mechanics(shop_id)
    chosen = next(m for m in mechanics if m.id == result.appointment.mechanic_id)
    assert any(s.repair_type == "engine" for s in chosen.skills)


@pytest.mark.asyncio
async def test_service_duration_sets_end_time(runtime, shop_id):
    """Catalog duration drives end_time (Oil Change 30m / Brake Repair 120m)."""
    oil_id = uuid4()
    oil = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=oil_id,
            service_name="Oil Change",
            repair_type="oil_change",
            estimated_duration_min=30,
        )
    )
    assert oil.success and oil.appointment
    assert oil.appointment.service_id == oil_id
    assert oil.appointment.estimated_duration_min == 30
    assert (oil.appointment.end - oil.appointment.start) == timedelta(minutes=30)

    brake_id = uuid4()
    brake = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=brake_id,
            service_name="Brake Repair",
            repair_type="brakes",
            estimated_duration_min=120,
        )
    )
    assert brake.success and brake.appointment
    assert brake.appointment.service_id == brake_id
    assert (brake.appointment.end - brake.appointment.start) == timedelta(minutes=120)


@pytest.mark.asyncio
async def test_required_skill_and_bay_enforced(runtime, shop_id):
    """Service skill/bay preferences drive mechanic + bay assignment when free."""
    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=uuid4(),
            service_name="Oil Change",
            repair_type="oil_change",
            required_bay="quick_service",
            estimated_duration_min=30,
        )
    )
    assert result.success and result.appointment
    mechanics = await runtime.service.list_mechanics(shop_id)
    bays = await runtime.service.list_bays(shop_id)
    chosen_mech = next(m for m in mechanics if m.id == result.appointment.mechanic_id)
    chosen_bay = next(b for b in bays if b.id == result.appointment.bay_id)
    assert any(s.repair_type == "oil_change" for s in chosen_mech.skills)
    assert chosen_bay.bay_type == "quick_service"
    assert result.appointment.metadata.get("required_skill") == "oil_change"
    assert result.appointment.metadata.get("required_bay") == "quick_service"


@pytest.mark.asyncio
async def test_rejects_when_no_mechanic_has_required_skill(runtime, shop_id):
    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="alignment",  # no seeded mechanic has this skill
            required_bay="alignment",
        )
    )
    assert not result.success
    assert result.message
    assert "skill" in result.message.lower() or "slots" in result.message.lower()


@pytest.mark.asyncio
async def test_bay_type_falls_back_when_preferred_busy(runtime, shop_id):
    """Preferred bay type is soft — free lanes of other types still book."""
    store = runtime.service._store
    # Only one quick_service lane; other lanes are general.
    store.set_bays(
        shop_id,
        [
            Bay(id=uuid4(), shop_id=shop_id, name="Bay 1", bay_type="quick_service"),
            Bay(id=uuid4(), shop_id=shop_id, name="Bay 2", bay_type="general"),
            Bay(id=uuid4(), shop_id=shop_id, name="Bay 3", bay_type="general"),
        ],
    )
    hours = await store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=30) <= window[1]:
            break
    assert preferred is not None

    booked = []
    for _ in range(3):
        booked.append(
            await runtime.service.book(
                BookingRequest(
                    shop_id=shop_id,
                    repair_type="oil_change",
                    required_bay="quick_service",
                    preferred_start=preferred,
                    estimated_duration_min=30,
                )
            )
        )
    assert all(r.success for r in booked)
    bay_types = []
    bays = {b.id: b for b in await store.list_bays(shop_id)}
    for r in booked:
        bay_types.append(bays[r.appointment.bay_id].bay_type)
    assert bay_types.count("quick_service") == 1
    assert bay_types.count("general") == 2


@pytest.mark.asyncio
async def test_parallel_intake_matches_team_size(runtime, shop_id):
    """Same-time bookings should succeed up to mechanic count, not bay-type count."""
    store = runtime.service._store
    mechanics = await store.list_mechanics(shop_id)
    assert len(mechanics) >= 3

    # Undersized: only 2 lanes → max 2 parallel.
    store.set_bays(
        shop_id,
        [
            Bay(id=uuid4(), shop_id=shop_id, name="Bay — General", bay_type="general"),
            Bay(
                id=uuid4(),
                shop_id=shop_id,
                name="Bay — Quick",
                bay_type="quick_service",
            ),
        ],
    )
    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=30) <= window[1]:
            break
    assert preferred is not None

    undersized = []
    for _ in range(3):
        undersized.append(
            await runtime.service.book(
                BookingRequest(
                    shop_id=shop_id,
                    repair_type="brakes",
                    required_bay="general",
                    preferred_start=preferred,
                    estimated_duration_min=30,
                )
            )
        )
    # Only 2 lanes can run in parallel at preferred; 3rd is rejected with alternatives.
    at_preferred = [
        r
        for r in undersized
        if r.success and r.appointment and r.appointment.start == preferred
    ]
    assert len(at_preferred) == 2
    assert sum(1 for r in undersized if r.success) == 2
    rejected = next(r for r in undersized if not r.success)
    assert rejected.conflicts and rejected.conflicts.has_conflict
    assert rejected.alternatives

    # Team-sized lanes restore full parallel intake.
    store.set_bays(
        shop_id,
        [
            Bay(
                id=uuid4(),
                shop_id=shop_id,
                name=f"Bay {i + 1}",
                bay_type="general",
            )
            for i in range(len(mechanics))
        ],
    )
    preferred2 = preferred + timedelta(hours=2)
    scaled = []
    for _ in range(3):
        scaled.append(
            await runtime.service.book(
                BookingRequest(
                    shop_id=shop_id,
                    repair_type="brakes",
                    required_bay="general",
                    preferred_start=preferred2,
                    estimated_duration_min=30,
                )
            )
        )
    assert sum(1 for r in scaled if r.success) == 3


@pytest.mark.asyncio
async def test_overflow_preferred_time_rejects_with_alternatives(runtime, shop_id):
    """When parallel capacity is full at preferred time, warn — do not auto-shift."""
    store = runtime.service._store
    mechanics = await store.list_mechanics(shop_id)
    assert len(mechanics) >= 3
    store.set_bays(
        shop_id,
        [
            Bay(id=uuid4(), shop_id=shop_id, name=f"Bay {i + 1}", bay_type="general")
            for i in range(len(mechanics))
        ],
    )
    hours = await store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=30) <= window[1]:
            break
    assert preferred is not None

    for _ in range(len(mechanics)):
        filled = await runtime.service.book(
            BookingRequest(
                shop_id=shop_id,
                repair_type="oil_change",
                preferred_start=preferred,
                estimated_duration_min=30,
            )
        )
        assert filled.success

    overflow = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="oil_change",
            preferred_start=preferred,
            estimated_duration_min=30,
        )
    )
    assert not overflow.success
    assert overflow.conflicts and overflow.conflicts.has_conflict
    assert overflow.alternatives
    assert overflow.recommended_slot is not None
    assert overflow.recommended_slot.start != preferred
    msg = (overflow.message or "").lower()
    assert "available" in msg or "unavailable" in msg or "conflict" in msg


@pytest.mark.asyncio
async def test_agent_validate_rejects_full_preferred_time(runtime, shop_id):
    """Voice/SMS VALIDATE_APPOINTMENT must refuse times at Team capacity."""
    from app.plugins.scheduling.availability.service import AvailabilityPluginService

    store = runtime.service._store
    mechanics = await store.list_mechanics(shop_id)
    store.set_bays(
        shop_id,
        [
            Bay(id=uuid4(), shop_id=shop_id, name=f"Bay {i + 1}", bay_type="general")
            for i in range(len(mechanics))
        ],
    )
    hours = await store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=30) <= window[1]:
            break
    assert preferred is not None

    for _ in range(len(mechanics)):
        filled = await runtime.service.book(
            BookingRequest(
                shop_id=shop_id,
                repair_type="oil_change",
                preferred_start=preferred,
                estimated_duration_min=30,
            )
        )
        assert filled.success

    avail = AvailabilityPluginService(
        store=runtime.agent_store, intelligence=runtime.service
    )
    end = preferred + timedelta(minutes=30)
    validation = await avail.validate_appointment(shop_id, start=preferred, end=end)
    assert not validation["valid"]
    assert validation["has_conflict"]
    joined = " ".join(validation.get("errors") or []).lower()
    assert "staff" in joined or "bay" in joined or "available" in joined

    free = preferred + timedelta(hours=2)
    free_ok = await avail.validate_appointment(
        shop_id, start=free, end=free + timedelta(minutes=30)
    )
    assert free_ok["valid"]


@pytest.mark.asyncio
async def test_overlap_blocked_for_same_mechanic_bay(runtime, shop_id):
    first = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=uuid4(),
            service_name="Oil Change",
            repair_type="oil_change",
            estimated_duration_min=30,
            priority="normal",
        )
    )
    assert first.success and first.appointment
    # Force exact same window — should conflict or be shifted away
    second = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=uuid4(),
            service_name="Brake Repair",
            repair_type="brakes",
            estimated_duration_min=120,
            preferred_start=first.appointment.start,
            mechanic_id=first.appointment.mechanic_id,
            bay_id=first.appointment.bay_id,
            priority="normal",
        )
    )
    if second.success and second.appointment:
        assert not (
            first.appointment.start < second.appointment.end
            and second.appointment.start < first.appointment.end
            and second.appointment.mechanic_id == first.appointment.mechanic_id
            and second.appointment.bay_id == first.appointment.bay_id
        )
    else:
        assert second.conflicts is not None and second.conflicts.has_conflict


@pytest.mark.asyncio
async def test_change_service_updates_duration_and_metadata(runtime, shop_id):
    from decimal import Decimal

    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        preferred = window[0].replace(hour=10, minute=0)
        if preferred >= window[0] and preferred + timedelta(minutes=90) <= window[1]:
            break
    assert preferred is not None

    booked = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=uuid4(),
            service_name="Oil Change",
            repair_type="oil_change",
            preferred_start=preferred,
            estimated_duration_min=30,
            estimated_revenue=Decimal("49.00"),
        )
    )
    assert booked.success and booked.appointment
    appt_id = booked.appointment.id
    new_service_id = uuid4()

    changed = await runtime.service.change_service(
        shop_id=shop_id,
        appointment_id=appt_id,
        service_id=new_service_id,
        service_name="Brake Job",
        repair_type="brakes",
        required_bay="general",
        estimated_duration_min=60,
        estimated_revenue=Decimal("199.00"),
    )
    assert changed.success
    assert changed.appointment is not None
    assert changed.appointment.service_id == new_service_id
    assert changed.appointment.repair_type == "brakes"
    assert changed.appointment.estimated_duration_min == 60
    assert changed.appointment.end == preferred + timedelta(minutes=60)
    assert changed.appointment.metadata.get("service_name") == "Brake Job"
    assert changed.appointment.estimated_revenue == Decimal("199.00")


@pytest.mark.asyncio
async def test_change_service_rejects_cancelled(runtime, shop_id):
    from decimal import Decimal

    booked = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            service_id=uuid4(),
            service_name="Oil Change",
            repair_type="oil_change",
            estimated_duration_min=30,
        )
    )
    assert booked.success and booked.appointment
    await runtime.service.cancel(
        shop_id=shop_id, appointment_id=booked.appointment.id, reason="test"
    )

    changed = await runtime.service.change_service(
        shop_id=shop_id,
        appointment_id=booked.appointment.id,
        service_id=uuid4(),
        service_name="Brakes",
        repair_type="brakes",
        required_bay=None,
        estimated_duration_min=60,
        estimated_revenue=Decimal("100.00"),
    )
    assert not changed.success
    assert "cancelled" in (changed.message or "").lower()


@pytest.mark.asyncio
async def test_walk_in_start_books_in_progress_during_hours(runtime, shop_id):
    """Start Service Visit lands on the schedule at the counter moment (open hours)."""
    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    preferred = None
    for offset in range(0, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        # Mid-window so duration fits inside business hours.
        mid = window[0] + (window[1] - window[0]) / 2
        preferred = mid.replace(second=0, microsecond=0)
        if preferred + timedelta(minutes=45) <= window[1]:
            break
    assert preferred is not None

    walk_in_id = uuid4()
    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="brakes",
            vehicle_type="sedan",
            source="walk_in",
            walk_in_id=walk_in_id,
            notes="Walk-in brakes",
            preferred_start=preferred,
            estimated_duration_min=45,
        )
    )
    assert result.success
    assert result.appointment is not None
    assert result.appointment.status == "in_progress"
    assert result.appointment.source == "walk_in"
    assert result.appointment.walk_in_id == walk_in_id
    assert result.appointment.start == preferred
    assert result.appointment.end == preferred + timedelta(minutes=45)


@pytest.mark.asyncio
async def test_walk_in_start_rejects_outside_business_hours(runtime, shop_id):
    hours = await runtime.service._store.list_business_hours(shop_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    closed_start = None
    for offset in range(1, 8):
        day = (now + timedelta(days=offset)).date()
        window = runtime.service._availability.day_window(hours, day)
        if window is None:
            continue
        # After close — outside business hours (future so it is not clamped to now).
        closed_start = window[1] + timedelta(minutes=30)
        break
    assert closed_start is not None

    result = await runtime.service.book(
        BookingRequest(
            shop_id=shop_id,
            repair_type="brakes",
            source="walk_in",
            walk_in_id=uuid4(),
            preferred_start=closed_start,
            estimated_duration_min=45,
        )
    )
    assert not result.success
    assert "business hours" in (result.message or "").lower()
