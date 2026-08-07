"""Cross-turn date/time composition after partial answers or unavailable slots."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.agents.base.agent import AgentContext
from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ
from app.agents.orchestrator import AgentOrchestrator


def _orch() -> AgentOrchestrator:
    # merge logic is pure; skip full construction.
    return AgentOrchestrator.__new__(AgentOrchestrator)


def test_alternate_day_reuses_prior_clock_after_unavailable_stash():
    """After Friday 3pm fails, 'Monday' alone must rebind Monday 3pm (not re-ask time)."""
    orch = _orch()
    # Prior complete pick kept as time_only so the hour survives unavailable.
    friday_3pm = datetime(2026, 8, 7, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    monday = datetime(2026, 8, 10, 8, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": friday_3pm.isoformat(),
            "pending_preferred_end": (friday_3pm.replace(hour=16)).isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": False,
            "pending_needs_time": False,
            "pending_service": "Oil Change",
        },
    )
    entities = {
        "preferred_start": monday.isoformat(),
        "preferred_end": monday.replace(hour=17).isoformat(),
        "time_precision": "day",
        "needs_time": True,
        "requested_service": "Oil Change",
    }
    merged = orch._merge_booking_context(entities, ctx, intent="book_appointment")
    assert merged.get("needs_time") is None or merged.get("needs_time") is not True
    assert merged.get("needs_date") is None or merged.get("needs_date") is not True
    assert merged.get("time_precision") == "clock"
    start = merged["preferred_start"]
    assert isinstance(start, datetime)
    local = start.astimezone(DEFAULT_SHOP_TZ)
    assert local.weekday() == 0  # Monday
    assert local.hour == 15


def test_alternate_time_reuses_prior_day_after_unavailable_stash():
    """After Friday 3pm fails, '4pm' alone must rebind Friday 4pm (not re-ask day)."""
    orch = _orch()
    friday_3pm = datetime(2026, 8, 7, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    # Provisional "today" 4pm as time-only parse (day not explicit on this turn).
    four_pm = datetime(2026, 8, 3, 16, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": friday_3pm.isoformat(),
            "pending_preferred_end": friday_3pm.replace(hour=16).isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": False,
            "pending_needs_time": False,
            "pending_service": "Oil Change",
        },
    )
    entities = {
        "preferred_start": four_pm.isoformat(),
        "preferred_end": four_pm.replace(hour=17).isoformat(),
        "time_precision": "clock",
        "needs_date": True,
        "requested_service": "Oil Change",
    }
    merged = orch._merge_booking_context(entities, ctx, intent="book_appointment")
    assert merged.get("needs_date") is None or merged.get("needs_date") is not True
    assert merged.get("needs_time") is None or merged.get("needs_time") is not True
    assert merged.get("time_precision") == "clock"
    local = merged["preferred_start"].astimezone(DEFAULT_SHOP_TZ)
    assert local.weekday() == 4  # still Friday
    assert local.hour == 16


def test_alternate_time_reuses_day_after_time_aspect_stash():
    """Time-unavailable stash (day precision) + '4pm' reuses that day."""
    orch = _orch()
    friday_3pm = datetime(2026, 8, 7, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    four_pm = datetime(2026, 8, 3, 16, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": friday_3pm.isoformat(),
            "pending_preferred_end": friday_3pm.replace(hour=16).isoformat(),
            "pending_time_precision": "day",
            "pending_needs_date": False,
            "pending_needs_time": True,
            "pending_service": "Oil Change",
        },
    )
    entities = {
        "preferred_start": four_pm.isoformat(),
        "preferred_end": four_pm.replace(hour=17).isoformat(),
        "time_precision": "clock",
        "needs_date": True,
        "requested_service": "Oil Change",
    }
    merged = orch._merge_booking_context(entities, ctx, intent="book_appointment")
    assert merged.get("time_precision") == "clock"
    local = merged["preferred_start"].astimezone(DEFAULT_SHOP_TZ)
    assert local.weekday() == 4
    assert local.hour == 16


def test_time_only_without_known_day_still_needs_date():
    """Bare 3pm then 4pm (never chose a day) must keep asking for the day."""
    orch = _orch()
    three = datetime(2026, 8, 3, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    four = datetime(2026, 8, 3, 16, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": three.isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": True,
            "pending_service": "Oil Change",
        },
    )
    entities = {
        "preferred_start": four.isoformat(),
        "time_precision": "clock",
        "needs_date": True,
    }
    merged = orch._merge_booking_context(entities, ctx, intent="book_appointment")
    assert merged.get("needs_date") is True
    assert merged.get("time_precision") == "time_only"


def test_time_only_stash_without_slots_forces_needs_date():
    """Carried time_only after closed day must re-ask day only, keeping the clock."""
    orch = _orch()
    three_pm = datetime(2026, 8, 8, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": three_pm.isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": True,
            "pending_service": "Oil Change",
            "pending_action": "book",
        },
    )
    merged = orch._merge_booking_context(
        {"requested_service": "Oil Change"},
        ctx,
        intent="book_appointment",
    )
    assert merged.get("time_precision") == "time_only"
    assert merged.get("needs_date") is True
    assert merged.get("needs_time") is None or merged.get("needs_time") is not True
    start = merged["preferred_start"]
    assert isinstance(start, datetime)
    assert start.astimezone(DEFAULT_SHOP_TZ).hour == 15


def test_held_slot_does_not_carry_stale_time_only_over_offer():
    """Successful hold must bind YES/name to slots_offered, not a orphan time_only."""
    orch = _orch()
    held = datetime(2026, 8, 10, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    stale = datetime(2026, 8, 8, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": stale.isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": False,
            "pending_needs_time": False,
            "pending_service": "Oil Change",
            "pending_action": "book",
            "slots_offered": [
                {"start": held.isoformat(), "end": held.isoformat()},
            ],
        },
    )
    merged = orch._merge_booking_context(
        {"booking_confirmed": True, "requested_service": "Oil Change"},
        ctx,
        intent="book_appointment",
    )
    start = merged["preferred_start"]
    assert isinstance(start, datetime)
    assert start.astimezone(DEFAULT_SHOP_TZ).hour == 10
    assert start.astimezone(DEFAULT_SHOP_TZ).day == 10



def test_day_after_time_only_with_needs_date_flag():
    """Initial time-only (needs_date) + day rebind."""
    orch = _orch()
    three_pm = datetime(2026, 8, 7, 15, 0, tzinfo=DEFAULT_SHOP_TZ)
    friday = datetime(2026, 8, 7, 8, 0, tzinfo=DEFAULT_SHOP_TZ)
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_preferred_start": three_pm.isoformat(),
            "pending_time_precision": "time_only",
            "pending_needs_date": True,
            "pending_service": "Oil Change",
        },
    )
    entities = {
        "preferred_start": friday.isoformat(),
        "preferred_end": friday.replace(hour=17).isoformat(),
        "time_precision": "day",
        "needs_time": True,
    }
    merged = orch._merge_booking_context(entities, ctx, intent="book_appointment")
    assert merged.get("time_precision") == "clock"
    local = merged["preferred_start"].astimezone(DEFAULT_SHOP_TZ)
    assert local.weekday() == 4
    assert local.hour == 15


def test_reschedule_keeps_existing_service_when_not_named():
    orch = _orch()
    old_id = str(uuid4())
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "upcoming_appointments": [
                {
                    "id": old_id,
                    "service_name": "Oil Change",
                    "service_id": old_id,
                    "status": "booked",
                }
            ]
        },
    )
    merged = orch._merge_booking_context({}, ctx, intent="reschedule")
    assert merged.get("requested_service") == "Oil Change"
    assert merged.get("service_id") == old_id


def test_reschedule_prefers_pending_service_over_appointment():
    """Day/time follow-up after a service swap must keep the new service."""
    orch = _orch()
    oil_id = str(uuid4())
    brake_id = str(uuid4())
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "pending_service": "Brake Repair",
            "pending_service_id": brake_id,
            "pending_duration_minutes": 120,
            "pending_action": "reschedule",
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "service_name": "Oil Change",
                    "service_id": oil_id,
                    "status": "booked",
                }
            ],
        },
    )
    # Time answer only — no service tokens.
    merged = orch._merge_booking_context(
        {"preferred_start": "2026-08-08T15:00:00-07:00", "time_precision": "clock"},
        ctx,
        intent="reschedule",
    )
    assert merged.get("requested_service") == "Brake Repair"
    assert merged.get("service_id") == brake_id
    assert merged.get("duration_minutes") == 120


def test_reschedule_does_not_pin_old_service_id_for_new_named_service():
    """Customer asks to change to brakes; keep name free for catalog match."""
    orch = _orch()
    oil_id = str(uuid4())
    ctx = AgentContext(
        shop_id=uuid4(),
        metadata={
            "upcoming_appointments": [
                {
                    "id": str(uuid4()),
                    "service_name": "Oil Change",
                    "service_id": oil_id,
                    "status": "booked",
                }
            ]
        },
    )
    entities = {"requested_service": "Brake Repair"}
    merged = orch._merge_booking_context(entities, ctx, intent="reschedule")
    assert merged.get("requested_service") == "Brake Repair"
    assert merged.get("service_id") is None
