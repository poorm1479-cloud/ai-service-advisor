"""Scheduling agent tests — AI decides; Workflow executes."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.agents.base.agent import AgentResult
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.scheduling.models import SchedulingAction, SchedulingRequest
from app.agents.scheduling.service import SchedulingAgent


async def _decide_and_apply(agent: SchedulingAgent, request: SchedulingRequest, context):
    result = await agent.process(request, context)
    decision = collect_decision(result)
    if decision is None:
        return result
    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[decision],
        ports=ports_from_agents(scheduling=agent),
        context=context,
    )
    if applied and applied.scheduling_result:
        return AgentResult.ok(applied.scheduling_result)
    return result


@pytest.mark.asyncio
async def test_list_slots_and_book(context):
    agent = SchedulingAgent()
    slots = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert slots.success
    assert len(slots.data.available_slots) > 0
    start = slots.data.available_slots[0].start

    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=start,
            time_precision="clock",
        ),
        context,
    )
    assert booked.success
    assert booked.data.success
    assert booked.data.appointment is not None
    assert len(booked.data.reminders) == 2


@pytest.mark.asyncio
async def test_reschedule_and_cancel(context):
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    start = openings.data.available_slots[0].start
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=start,
            time_precision="clock",
        ),
        context,
    )
    appt_id = booked.data.appointment.id

    rescheduled = await _decide_and_apply(
        agent,
        SchedulingRequest(action=SchedulingAction.RESCHEDULE, appointment_id=appt_id),
        context,
    )
    assert rescheduled.success
    assert rescheduled.data.appointment is not None

    cancelled = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.CANCEL,
            appointment_id=rescheduled.data.appointment.id,
            reason="customer request",
        ),
        context,
    )
    assert cancelled.success
    assert cancelled.data.appointment.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_without_appointment_is_soft(context):
    """Missing appointment must not fail the agent stage (which escalates the call)."""
    agent = SchedulingAgent()
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="cancel_appointment",
        ),
        context,
    )
    assert result.success
    assert result.data is not None
    assert result.data.success is False
    assert result.data.message == "no_appointment_to_cancel"
    assert result.data.decision is not None
    assert result.data.decision.action == "noop"


@pytest.mark.asyncio
async def test_reschedule_without_appointment_is_soft(context):
    """Missing appointment must not emit a mutative reschedule decision."""
    agent = SchedulingAgent()
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="reschedule",
        ),
        context,
    )
    assert result.success
    assert result.data is not None
    assert result.data.success is False
    assert result.data.message == "no_appointment_to_reschedule"
    assert result.data.decision is not None
    assert result.data.decision.action == "noop"


@pytest.mark.asyncio
async def test_book_after_conversation_booking_reschedules_previous(context):
    """Time change after AI already booked must not leave the old slot active."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first_start = openings.data.available_slots[0].start
    second_start = openings.data.available_slots[3].start

    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first_start,
            time_precision="clock",
        ),
        context,
    )
    assert booked.data.appointment is not None
    old_id = booked.data.appointment.id
    context.metadata["appointment_id"] = str(old_id)

    moved = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            appointment_id=old_id,
            preferred_start=second_start,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert moved.success
    assert moved.data.success
    assert moved.data.appointment is not None
    assert moved.data.appointment.id != old_id
    assert moved.data.action == "reschedule"

    old = await agent.store.get(context.shop_id, old_id)
    assert old is not None
    assert old.status == "rescheduled"


@pytest.mark.asyncio
async def test_intent_maps_book_to_ask_preferred_time(context):
    agent = SchedulingAgent()
    result = await agent.process(
        SchedulingRequest(action=SchedulingAction.NOOP, intent="book_appointment"),
        context,
    )
    assert result.data.action == "list_slots"
    assert result.data.success
    assert result.data.message == "ask_preferred_time"
    assert result.data.available_slots == []
    assert result.data.decision is not None
    assert result.data.decision.action == "list_slots"
    assert result.data.metadata.get("action") == "book"


@pytest.mark.asyncio
async def test_intent_maps_reschedule_to_ask_preferred_time(context):
    """Bare time-change ask must not invent a slot — ask for the new time."""
    from uuid import uuid4

    agent = SchedulingAgent()
    appt_id = uuid4()
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="reschedule",
            appointment_id=appt_id,
            requested_service="Oil Change",
        ),
        context,
    )
    assert result.data is not None
    assert result.data.message == "ask_preferred_time"
    assert result.data.available_slots == []
    assert result.data.metadata.get("action") == "reschedule"
    assert (result.data.metadata or {}).get("pending_slot_start") is None
    assert result.data.decision is not None
    assert result.data.decision.appointment_id == appt_id
    assert result.data.decision.offer_policy == "ask_time"


@pytest.mark.asyncio
async def test_reschedule_holds_exact_spoken_clock_time(context):
    """Customer-spoken clock time must be the pending slot — not nearest opening."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0].start
    later = openings.data.available_slots[5].start
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first,
            time_precision="clock",
        ),
        context,
    )
    appt_id = booked.data.appointment.id

    hold = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="reschedule",
            appointment_id=appt_id,
            preferred_start=later,
            time_precision="clock",
        ),
        context,
    )
    assert hold.data.message == "awaiting_reschedule_confirmation"
    assert hold.data.metadata.get("pending_slot_start") == later.isoformat()
    assert hold.data.decision is not None
    assert hold.data.decision.recommended_slot_start == later


@pytest.mark.asyncio
async def test_reschedule_unavailable_clock_does_not_snap(context):
    """Non-matching clock time must not silently move to the next opening."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0].start
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first,
            time_precision="clock",
        ),
        context,
    )
    appt_id = booked.data.appointment.id
    weird = first.replace(minute=17) + __import__("datetime").timedelta(days=1)

    hold = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="reschedule",
            appointment_id=appt_id,
            preferred_start=weird,
            time_precision="clock",
        ),
        context,
    )
    assert hold.data.message == "preferred_time_unavailable"
    assert hold.data.metadata.get("action") == "reschedule"
    assert (hold.data.metadata or {}).get("pending_slot_start") is None


@pytest.mark.asyncio
async def test_reschedule_confirm_unavailable_does_not_snap(context):
    """YES on a preferred time that is free nowhere must refuse, not book next slot."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0].start
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    appt_id = booked.data.appointment.id
    weird = first.replace(minute=17) + __import__("datetime").timedelta(days=1)

    moved = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.RESCHEDULE,
            appointment_id=appt_id,
            preferred_start=weird,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert moved.data is not None
    assert not moved.data.success or moved.data.appointment is None
    assert moved.data.message == "preferred_time_unavailable"
    assert moved.data.appointment is None
    # Original booking remains active.
    old = await agent.store.get(context.shop_id, appt_id)
    assert old is not None
    assert old.status == "booked"


@pytest.mark.asyncio
async def test_book_with_pending_reschedule_moves_existing(context):
    """pending_action=reschedule + appointment_id must reschedule, not duplicate."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0].start
    later = openings.data.available_slots[5].start
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first,
            time_precision="clock",
        ),
        context,
    )
    old_id = booked.data.appointment.id
    context.metadata["pending_action"] = "reschedule"
    # No memory appointment_id — only upcoming-resolved id on the request.

    moved = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            appointment_id=old_id,
            preferred_start=later,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert moved.success
    assert moved.data.success
    assert moved.data.action == "reschedule"
    assert moved.data.appointment is not None
    assert moved.data.appointment.start == later
    old = await agent.store.get(context.shop_id, old_id)
    assert old is not None
    assert old.status == "rescheduled"


@pytest.mark.asyncio
async def test_reschedule_can_change_service(context):
    """Voice/SMS appointment moves must persist a newly requested catalog service."""
    from app.agents.scheduling.catalog_port import InMemoryServiceCatalog

    catalog = InMemoryServiceCatalog()
    seed = catalog.seed_from_starter(context.shop_id)
    oil = next(s for s in seed if s.name == "Oil Change")
    brake = next(s for s in seed if s.name == "Brake Repair")
    agent = SchedulingAgent(catalog=catalog)
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0].start
    later = openings.data.available_slots[4].start

    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            preferred_start=first,
            time_precision="clock",
            requested_service="Oil Change",
            service_id=oil.id,
            confirm_booking=True,
        ),
        context,
    )
    assert booked.data.appointment is not None
    assert booked.data.appointment.service_id == oil.id
    old_id = booked.data.appointment.id

    moved = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.RESCHEDULE,
            appointment_id=old_id,
            preferred_start=later,
            time_precision="clock",
            requested_service="Brake Repair",
            service_id=brake.id,
            confirm_booking=True,
        ),
        context,
    )
    assert moved.success
    assert moved.data.success
    assert moved.data.appointment is not None
    assert moved.data.appointment.id != old_id
    assert moved.data.appointment.start == later
    assert moved.data.appointment.service_id == brake.id
    assert moved.data.appointment.service_name == "Brake Repair"
    old = await agent.store.get(context.shop_id, old_id)
    assert old is not None
    assert old.status == "rescheduled"


@pytest.mark.asyncio
async def test_intent_maps_availability_to_list_slots(context):
    agent = SchedulingAgent()
    result = await agent.process(
        SchedulingRequest(action=SchedulingAction.NOOP, intent="check_availability"),
        context,
    )
    assert result.data.action == "list_slots"
    assert result.data.success
    assert len(result.data.available_slots) > 0


@pytest.mark.asyncio
async def test_confirmed_book_intent_books(context):
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    start = openings.data.available_slots[0].start
    result = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=start,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert result.data.action == "book"
    assert result.data.success
    assert result.data.appointment is not None


@pytest.mark.asyncio
async def test_book_without_preferred_time_asks_for_time(context):
    """Must ask when they want to come — never invent or volunteer the first slot."""
    agent = SchedulingAgent()
    result = await agent.process(
        SchedulingRequest(action=SchedulingAction.BOOK),
        context,
    )
    assert result.data.action == "list_slots"
    assert result.data.message == "ask_preferred_time"
    assert result.data.available_slots == []
    assert result.data.decision is not None
    assert result.data.decision.recommended_slot_start is None
    assert result.data.appointment is None


@pytest.mark.asyncio
async def test_prefer_earliest_selects_first_opening(context):
    """Explicit earliest/first-available may select the first free opening to confirm."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    first = openings.data.available_slots[0]
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=first.start,
            time_precision="day",
            prefer_earliest=True,
        ),
        context,
    )
    assert result.data.message == "awaiting_booking_confirmation"
    assert result.data.decision is not None
    assert result.data.decision.recommended_slot_start == first.start
    assert result.data.metadata.get("prefer_earliest") is True


@pytest.mark.asyncio
async def test_prefer_latest_selects_last_opening(context):
    """Explicit last-available may select the last free opening to confirm."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=7),
        context,
    )
    day_slots = openings.data.available_slots
    assert day_slots
    # Prefer latest within the first shop day so day-filter + days_ahead agree.
    first_day = day_slots[0].start.date()
    same_day = [s for s in day_slots if s.start.date() == first_day]
    last = same_day[-1]
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=last.start.replace(hour=8, minute=0),
            preferred_end=last.start.replace(hour=17, minute=0),
            time_precision="day",
            prefer_latest=True,
            days_ahead=7,
        ),
        context,
    )
    assert result.data.message == "awaiting_booking_confirmation"
    assert result.data.decision is not None
    assert result.data.decision.recommended_slot_start == last.start
    assert result.data.metadata.get("prefer_latest") is True


@pytest.mark.asyncio
async def test_part_of_day_asks_for_clock_time(context):
    """'tomorrow morning' must not invent 9am or volunteer openings."""
    agent = SchedulingAgent()
    all_slots = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert all_slots.data.available_slots
    preferred = all_slots.data.available_slots[0].start.replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    preferred_end = preferred.replace(hour=11)

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=preferred,
            preferred_end=preferred_end,
            time_precision="part_of_day",
            days_ahead=14,
        ),
        context,
    )
    assert pending.data.action == "list_slots"
    assert pending.data.message == "ask_preferred_time"
    assert not pending.data.metadata.get("pending_slot_start")
    assert pending.data.available_slots == []


@pytest.mark.asyncio
async def test_preferred_start_awaits_confirmation_then_books(context):
    agent = SchedulingAgent()
    slots = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert slots.data.available_slots
    # Prefer a mid-list opening so we know selection isn't always slot[0].
    target = slots.data.available_slots[min(3, len(slots.data.available_slots) - 1)].start
    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=target,
            time_precision="clock",
        ),
        context,
    )
    assert pending.data.action == "list_slots"
    assert pending.data.message == "awaiting_booking_confirmation"
    assert pending.data.metadata.get("pending_slot_start") == target.isoformat()

    result = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=target,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert result.data.action == "book"
    assert result.data.appointment is not None
    assert result.data.appointment.start == target


@pytest.mark.asyncio
async def test_unavailable_preferred_start_rejects_without_suggesting(context):
    """Taken clock time → unavailable; do not auto-pick the next opening."""
    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    start = openings.data.available_slots[0].start
    # Book the opening so a later request for the same clock time fails.
    booked = await _decide_and_apply(
        agent,
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=start,
            time_precision="clock",
            confirm_booking=True,
        ),
        context,
    )
    assert booked.data.appointment is not None

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=start,
            time_precision="clock",
        ),
        context,
    )
    assert pending.data.message == "preferred_time_unavailable"
    assert pending.data.available_slots == []
    assert not pending.data.metadata.get("pending_slot_start")
    assert pending.data.metadata.get("unavailable_aspect") == "time"


@pytest.mark.asyncio
async def test_outside_business_hours_preferred_is_unavailable(context):
    """Clock time outside shop hours must not become a booking confirmation."""
    from zoneinfo import ZoneInfo

    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert openings.data.available_slots
    day = openings.data.available_slots[0].start
    la = ZoneInfo("America/Los_Angeles")
    outside = day.astimezone(la).replace(hour=20, minute=0, second=0, microsecond=0)

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=outside,
            time_precision="clock",
            days_ahead=14,
        ),
        context,
    )
    assert pending.data.message == "preferred_time_unavailable"
    assert pending.data.available_slots == []
    assert not pending.data.metadata.get("pending_slot_start")
    # Same day still has openings → re-ask clock only
    assert pending.data.metadata.get("unavailable_aspect") == "time"


@pytest.mark.asyncio
async def test_closed_day_preferred_marks_date_unavailable_aspect(context):
    """Preferred clock on a day with no openings → re-ask day only (keep hour)."""
    from zoneinfo import ZoneInfo

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert openings.data.available_slots
    # Pick a Sunday well beyond the open window if the store only opens weekdays.
    # Walk forward from first opening until a local date with zero same-day slots.
    la = DEFAULT_SHOP_TZ
    first = openings.data.available_slots[0].start.astimezone(la)
    all_days = {
        s.start.astimezone(la).date() for s in openings.data.available_slots
    }
    closed = None
    probe = first
    for _ in range(14):
        probe = probe + __import__("datetime").timedelta(days=1)
        if probe.date() not in all_days:
            closed = probe.replace(hour=10, minute=0, second=0, microsecond=0)
            break
    if closed is None:
        # Store has openings every day — fall back to outside window far future.
        closed = first.replace(year=first.year + 1, month=1, day=1, hour=10)

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=closed,
            time_precision="clock",
            days_ahead=14,
        ),
        context,
    )
    assert pending.data.message == "preferred_time_unavailable"
    aspect = pending.data.metadata.get("unavailable_aspect")
    assert aspect in {"date", "both"}
    if any(s.start.astimezone(la).date() != closed.date() for s in openings.data.available_slots):
        # Other days exist in listing → date aspect
        if any(
            s.start.astimezone(la).date() == d
            for s in openings.data.available_slots
            for d in all_days
            if d != closed.date()
        ):
            assert aspect == "date"


@pytest.mark.asyncio
async def test_day_only_preference_asks_for_clock_time(context):
    """Day-only must ask for a clock time — not volunteer day's openings."""
    agent = SchedulingAgent()
    all_slots = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert all_slots.data.available_slots
    preferred = all_slots.data.available_slots[0].start.replace(
        hour=8, minute=0, second=0, microsecond=0
    )

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=preferred,
            time_precision="day",
            days_ahead=14,
        ),
        context,
    )
    assert pending.data.action == "list_slots"
    assert pending.data.message == "ask_preferred_time"
    assert not pending.data.metadata.get("pending_slot_start")
    assert pending.data.available_slots == []


@pytest.mark.asyncio
async def test_closed_day_only_rejects_without_asking_time(context):
    """Day-only on a closed day must refuse immediately — never ask for a clock."""
    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    agent = SchedulingAgent()
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        context,
    )
    assert openings.data.available_slots
    la = DEFAULT_SHOP_TZ
    first = openings.data.available_slots[0].start.astimezone(la)
    open_days = {
        s.start.astimezone(la).date() for s in openings.data.available_slots
    }
    closed = None
    probe = first
    for _ in range(21):
        probe = probe + __import__("datetime").timedelta(days=1)
        if probe.date() not in open_days:
            closed = probe.replace(hour=8, minute=0, second=0, microsecond=0)
            break
    assert closed is not None, "need a closed calendar day in the open window"

    pending = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.NOOP,
            intent="book_appointment",
            preferred_start=closed,
            time_precision="day",
            days_ahead=14,
        ),
        context,
    )
    assert pending.data.message == "preferred_time_unavailable"
    assert pending.data.metadata.get("unavailable_aspect") == "date"
    assert pending.data.metadata.get("closed_day") is True
    assert pending.data.message != "ask_preferred_time"
    assert not pending.data.metadata.get("ask_preferred_time")
