"""Intent agent tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.communication.models import NormalizedMessage
from app.agents.intent.models import CustomerIntent
from app.agents.intent.service import IntentAgent
from app.agents.scheduling.catalog_port import CatalogServiceView, InMemoryServiceCatalog


def _msg(body: str) -> NormalizedMessage:
    return NormalizedMessage(
        channel="sms",
        direction="incoming",
        body=body,
        sender="+1",
        recipient=None,
        subject=None,
        received_at=None,
        language="en",
        metadata={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I need to book an appointment for Friday", CustomerIntent.BOOK_APPOINTMENT),
        ("I want to make a reservation", CustomerIntent.BOOK_APPOINTMENT),
        ("I'd like to book", CustomerIntent.BOOK_APPOINTMENT),
        ("Can I schedule something?", CustomerIntent.BOOK_APPOINTMENT),
        ("What times are available this week?", CustomerIntent.CHECK_AVAILABILITY),
        ("When can I come in for an oil change?", CustomerIntent.CHECK_AVAILABILITY),
        ("Do you have any openings tomorrow?", CustomerIntent.CHECK_AVAILABILITY),
        ("Please reschedule my appointment", CustomerIntent.RESCHEDULE),
        ("Can I change the appointment time?", CustomerIntent.RESCHEDULE),
        ("Can I change my appointment time?", CustomerIntent.RESCHEDULE),
        ("I want to change my appointment", CustomerIntent.RESCHEDULE),
        ("Is it possible to change my reservation time?", CustomerIntent.RESCHEDULE),
        ("I need an appointment time change", CustomerIntent.RESCHEDULE),
        ("reservation time change", CustomerIntent.RESCHEDULE),
        ("I want to change my time", CustomerIntent.RESCHEDULE),
        ("I need to make a reservation time change", CustomerIntent.RESCHEDULE),
        # Broader spoken variants
        ("I need to reschedule", CustomerIntent.RESCHEDULE),
        ("Can I reschedule?", CustomerIntent.RESCHEDULE),
        ("Move my appointment to Friday", CustomerIntent.RESCHEDULE),
        ("Can I move my visit?", CustomerIntent.RESCHEDULE),
        ("Change my booking", CustomerIntent.RESCHEDULE),
        ("Change the date", CustomerIntent.RESCHEDULE),
        ("I need a different day", CustomerIntent.RESCHEDULE),
        ("Can I do another day?", CustomerIntent.RESCHEDULE),
        ("Another time please", CustomerIntent.RESCHEDULE),
        ("Pick a different time", CustomerIntent.RESCHEDULE),
        ("That day does not work", CustomerIntent.RESCHEDULE),
        ("I can't make it", CustomerIntent.RESCHEDULE),
        ("Something came up", CustomerIntent.RESCHEDULE),
        ("Can we push it back?", CustomerIntent.RESCHEDULE),
        ("Push my appointment back", CustomerIntent.RESCHEDULE),
        ("Switch my appointment", CustomerIntent.RESCHEDULE),
        ("Modify my appointment", CustomerIntent.RESCHEDULE),
        ("Update my appointment", CustomerIntent.RESCHEDULE),
        ("I need a new time", CustomerIntent.RESCHEDULE),
        ("Can I come another day?", CustomerIntent.RESCHEDULE),
        ("I need to change it", CustomerIntent.RESCHEDULE),
        ("Is it possible to change?", CustomerIntent.RESCHEDULE),
        # STT / casual synonyms (reset ≈ reschedule)
        ("reset", CustomerIntent.RESCHEDULE),
        ("Reset please", CustomerIntent.RESCHEDULE),
        ("I need to reset", CustomerIntent.RESCHEDULE),
        ("Can I reset my appointment?", CustomerIntent.RESCHEDULE),
        ("Reset my booking", CustomerIntent.RESCHEDULE),
        ("replace", CustomerIntent.RESCHEDULE),
        ("Replace please", CustomerIntent.RESCHEDULE),
        ("I need to replace", CustomerIntent.RESCHEDULE),
        ("Can I replace my appointment?", CustomerIntent.RESCHEDULE),
        ("Replace my booking", CustomerIntent.RESCHEDULE),
        ("re-place my visit", CustomerIntent.RESCHEDULE),
        ("re-set my appointment", CustomerIntent.RESCHEDULE),
        ("I want to redo my appointment", CustomerIntent.RESCHEDULE),
        ("Can we adjust the time?", CustomerIntent.RESCHEDULE),
        ("Please postpone my visit", CustomerIntent.RESCHEDULE),
        ("I need to delay my appointment", CustomerIntent.RESCHEDULE),
        ("Can we shift it?", CustomerIntent.RESCHEDULE),
        ("Set a new time", CustomerIntent.RESCHEDULE),
        ("Let's reset", CustomerIntent.RESCHEDULE),
        ("Cancel my appointment please", CustomerIntent.CANCEL_APPOINTMENT),
        ("What's the status of my car repair?", CustomerIntent.ASK_REPAIR_STATUS),
        ("How much does a brake job cost?", CustomerIntent.PRICE_QUESTION),
        ("When should I get an oil change?", CustomerIntent.MAINTENANCE_QUESTION),
        ("I'm a first time customer", CustomerIntent.NEW_CUSTOMER),
        ("Book me for the first available time today", CustomerIntent.BOOK_APPOINTMENT),
        ("I'd like the earliest opening tomorrow", CustomerIntent.BOOK_APPOINTMENT),
        ("I'm returning again for my usual service", CustomerIntent.RETURNING_CUSTOMER),
        ("I want to file a complaint with the manager", CustomerIntent.COMPLAINT),
        ("This is an emergency — my car won't start and I'm stranded", CustomerIntent.EMERGENCY),
        ("Hello there", CustomerIntent.OTHER),
    ],
)
async def test_intent_detection(context, text, expected):
    agent = IntentAgent()
    result = await agent.detect(_msg(text), context)
    assert result.success
    assert result.data is not None
    assert result.data.intent == expected
    payload = result.data.to_json()
    assert payload["intent"] == expected.value
    assert "confidence" in payload


@pytest.mark.asyncio
async def test_entity_extraction(context):
    agent = IntentAgent()
    result = await agent.detect(
        _msg("Call me at 555-123-4567 about VIN 1HGCM82633A004352 with 45200 miles"),
        context,
    )
    assert result.data is not None
    assert "phone" in result.data.entities
    assert result.data.entities["vin"] == "1HGCM82633A004352"
    assert result.data.entities["mileage"] == 45200


@pytest.mark.asyncio
async def test_extracts_customer_name(context):
    agent = IntentAgent()
    result = await agent.detect(_msg("Hi, my name is Alex Rivera"), context)
    assert result.data is not None
    assert result.data.entities.get("name") == "Alex Rivera"

    context.metadata["pending_question"] = (
        "what's your name so I can put the booking under you?"
    )
    context.metadata["pending_action"] = "book"
    context.metadata["pending_service"] = "Oil Change"
    bare = await agent.detect(_msg("Sam"), context)
    assert bare.data is not None
    assert bare.data.entities.get("name") == "Sam"
    assert bare.data.intent == CustomerIntent.BOOK_APPOINTMENT


@pytest.mark.asyncio
async def test_does_not_extract_going_as_customer_name(context):
    """'I'm going …' must not become customer name 'Going' (Hello Going)."""
    agent = IntentAgent()
    for text in (
        "I'm going to book an oil change",
        "I'm going",
        "I am going tomorrow",
        "I'm gonna need brakes",
    ):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None
        assert result.data.entities.get("name") is None, text


@pytest.mark.asyncio
async def test_catalog_service_drives_booking_intent_and_entities(context):
    """Shop Services catalog grounds intent: custom names + desire → book."""
    service_id = uuid4()
    catalog = InMemoryServiceCatalog()
    catalog.seed_shop(
        context.shop_id,
        [
            CatalogServiceView(
                id=service_id,
                name="Euro Oil Service",
                category="maintenance",
                duration_minutes=35,
                skill="oil_change",
                bay="quick_service",
                price=Decimal("59.99"),
            )
        ],
    )
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("I need a Euro Oil Service"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("requested_service") == "Euro Oil Service"
    assert result.data.entities.get("service_id") == str(service_id)
    assert result.data.entities.get("duration_minutes") == 35
    assert result.data.entities.get("service_price") == "59.99"


@pytest.mark.asyncio
async def test_catalog_match_keeps_advisory_as_maintenance(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("When should I get an oil change?"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.MAINTENANCE_QUESTION
    assert result.data.entities.get("requested_service") == "Oil Change"


@pytest.mark.asyncio
async def test_need_oil_change_books_via_catalog(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("I need an oil change"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("requested_service") == "Oil Change"


@pytest.mark.asyncio
async def test_availability_ask_not_forced_to_book(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("What times are available for an oil change?"), context
    )
    assert result.data is not None
    assert result.data.intent == CustomerIntent.CHECK_AVAILABILITY
    assert result.data.entities.get("requested_service") == "Oil Change"


@pytest.mark.asyncio
async def test_oil_change_appointment_not_reschedule(context):
    """'oil change appointment' must not be mistaken for time-change intent."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("I need an oil change appointment"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.intent != CustomerIntent.RESCHEDULE


@pytest.mark.asyncio
async def test_reschedule_time_ask_does_not_attach_other_service(context):
    """Asking to change appointment time must not invent Oil Change (or any service)."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("Can I change my appointment time?"), context
    )
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("requested_service") is None
    assert result.data.entities.get("service_id") is None


@pytest.mark.asyncio
async def test_new_time_after_conversation_booking_is_reschedule(context):
    """After AI booked in-chat, a new day/time is a move — not a second booking."""
    context.metadata["appointment_id"] = str(uuid4())
    context.metadata["upcoming_appointments"] = [
        {
            "id": context.metadata["appointment_id"],
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent()
    result = await agent.detect(_msg("Actually make it Friday at 3pm"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("preferred_start")


@pytest.mark.asyncio
async def test_time_answer_during_reschedule_hold_stays_reschedule(context):
    """After ask-new-time, a clock answer must continue reschedule (not book)."""
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Oil Change"
    context.metadata["slots_offered"] = []
    # No appointment_id yet — SMS may only have pending_action until enrich.
    agent = IntentAgent()
    result = await agent.detect(_msg("Friday at 3pm"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("time_precision") == "clock"

@pytest.mark.asyncio
async def test_reschedule_with_named_service_keeps_service(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("Please reschedule my oil change"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("requested_service") == "Oil Change"


@pytest.mark.asyncio
async def test_reschedule_switch_target_picks_new_service(context):
    """'Change oil change to brake repair' must not stay on Oil Change."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    oil = next(
        s
        for s in await catalog.list_bookable_services(context.shop_id)
        if s.name == "Oil Change"
    )
    context.metadata["appointment_id"] = str(uuid4())
    context.metadata["upcoming_appointments"] = [
        {
            "id": context.metadata["appointment_id"],
            "service_name": "Oil Change",
            "service_id": str(oil.id),
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("I want to change my oil change to a brake repair"), context
    )
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("requested_service") == "Brake Repair"
    assert not result.data.entities.get("service_needs_disambiguation")


@pytest.mark.asyncio
async def test_change_service_type_is_reschedule(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("Please change the service type to brake repair"), context
    )
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("requested_service") == "Brake Repair"


@pytest.mark.asyncio
async def test_bare_change_service_type_is_reschedule(context):
    """'Change the service type' alone is a service swap intent (ask which next)."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("Please change the service type"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    # No destination named yet — leave service unset for the counselor ask.
    assert not result.data.entities.get("requested_service")


@pytest.mark.asyncio
async def test_change_both_service_and_time_is_reschedule(context):
    """Compound desire to change service type + clock must be reschedule."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    for text in (
        "Change both the service type and the time",
        "change the service type and the appointment time",
        "I need to change both the service and the time",
        "service and time change",
        "Can I change both the service and the date?",
        "I'd like to update the service type as well as the time",
        "switch the job and the day",
        "modify service plus time",
        "need a different service and a different time",
        "I need a new service and a new time",
        "change what and when",
        "reschedule with a different service and time",
        "both the service and the time",
        "change the time and the service too",
        "not just the time, the service too",
        "change the whole appointment",
        "swap service and time",
        "please change both service kind and date",
        "time and service update",
        "want a different job and another day",
    ):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text


@pytest.mark.asyncio
async def test_reschedule_hold_keeps_named_service_without_time(context):
    """Mid hold, answering only with the new job stays on reschedule."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["appointment_id"] = str(uuid4())
    context.metadata["pending_action"] = "reschedule"
    context.metadata["upcoming_appointments"] = [
        {
            "id": context.metadata["appointment_id"],
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("Brake repair"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    assert result.data.entities.get("requested_service") == "Brake Repair"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Can I swap the service?",
        "I booked the wrong service",
        "I need a different repair",
        "Change what I booked",
        "Switch to a different service",
        "Not the right service",
        "Update the type of service",
        "I want something else done",
        "Make it a different job",
    ],
)
async def test_service_type_synonyms_are_reschedule(context, text):
    """Spoken synonyms for service-type change must not be misread as a fresh book."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg(text), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE, text


@pytest.mark.asyncio
async def test_service_type_synonym_with_target_picks_service(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    for text in (
        "Swap the service type to brake repair",
        "Make it a brake repair",
        "Actually I need brake repair",
        "Change the type of service to brake repair",
    ):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text
        assert result.data.entities.get("requested_service") == "Brake Repair", text


@pytest.mark.asyncio
async def test_yes_sets_booking_confirmed(context):
    agent = IntentAgent()
    result = await agent.detect(_msg("YES"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("booking_confirmed") is True


@pytest.mark.asyncio
async def test_yes_please_and_go_ahead_are_affirmations(context):
    """Voice STT often appends courtesy words — still confirm when pending cancel."""
    agent = IntentAgent()
    for text in ("yes please", "yep go ahead", "go ahead", "sure thanks"):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.entities.get("booking_confirmed") is True, text
        assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT, text

    context.metadata["pending_cancel"] = True
    context.metadata["pending_action"] = "cancel"
    result = await agent.detect(_msg("yes please"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.CANCEL_APPOINTMENT
    assert result.data.entities.get("booking_confirmed") is True


@pytest.mark.asyncio
async def test_extracts_preferred_start_with_service(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("I need an oil change Tuesday at 2pm"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("requested_service") == "Oil Change"
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("time_precision") == "clock"
    assert not result.data.entities.get("needs_time")


@pytest.mark.asyncio
async def test_day_only_sets_needs_time(context):
    """'Friday' must not invent a clock time for booking confirmation."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("I need an oil change appointment for Friday"), context
    )
    assert result.data is not None
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("time_precision") == "day"
    assert result.data.entities.get("needs_time") is True
    assert result.data.entities.get("needs_date") is not True


@pytest.mark.asyncio
async def test_time_only_sets_needs_date(context):
    """'3pm' alone must not invent a day for booking confirmation."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    context.metadata["pending_service"] = "Oil Change"
    result = await agent.detect(_msg("3pm"), context)
    assert result.data is not None
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("needs_date") is True
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_part_of_day_sets_needs_time(context):
    """'tomorrow morning' must not invent 9am for booking confirmation."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("I need an oil change tomorrow morning"), context
    )
    assert result.data is not None
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("time_precision") == "part_of_day"
    assert result.data.entities.get("needs_time") is True


@pytest.mark.asyncio
async def test_first_available_today_prefers_earliest(context):
    """'Book the first available time today' → book + prefer_earliest, no needs_time."""
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(
        _msg("Book me for the first available time today for an oil change"),
        context,
    )
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("prefer_earliest") is True
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_today_at_hour_clock(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    context.metadata["pending_service"] = "Oil Change"
    result = await agent.detect(_msg("today at 3"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("time_precision") == "clock"
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_todays_first_slot(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("today's first"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("prefer_earliest") is True
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("time_precision") == "day"
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_tomorrows_first_slot(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("tomorrow's first available"), context)
    assert result.data is not None
    assert result.data.entities.get("prefer_earliest") is True
    assert result.data.entities.get("preferred_start")
    start = result.data.entities["preferred_start"]
    assert "T" in start  # isoformat


@pytest.mark.asyncio
async def test_morning_first_slot(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("morning first time"), context)
    assert result.data is not None
    assert result.data.entities.get("prefer_earliest") is True
    assert result.data.entities.get("time_precision") == "part_of_day"
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_afternoon_first_slot(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("afternoon first slot"), context)
    assert result.data is not None
    assert result.data.entities.get("prefer_earliest") is True
    assert result.data.entities.get("time_precision") == "part_of_day"


@pytest.mark.asyncio
async def test_last_available_slot(context):
    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("last available time"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("prefer_latest") is True
    assert result.data.entities.get("preferred_start")
    assert result.data.entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_day_time_followup_books_with_pending_slots(context):
    context.metadata["slots_offered"] = [
        {"start": "2026-08-04T09:00:00+00:00", "end": "2026-08-04T10:00:00+00:00"}
    ]
    context.metadata["pending_service"] = "Oil Change"
    agent = IntentAgent()
    result = await agent.detect(_msg("Tuesday at 2pm"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
    assert result.data.entities.get("preferred_start")


@pytest.mark.asyncio
async def test_same_time_reuses_existing_appointment_slot(context):
    """After service-type change, 'same time' keeps the booked day+clock."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Brake Repair"
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("same time"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.RESCHEDULE
    start = result.data.entities.get("preferred_start")
    assert start
    # preferred_start is stored as ISO; accept with or without offset form.
    assert "2026-08-12" in start
    assert "14:00" in start or "T14:00" in start
    assert result.data.entities.get("time_precision") == "clock"
    assert result.data.entities.get("needs_date") is not True
    assert result.data.entities.get("needs_time") is not True
    assert result.data.entities.get("same_slot_preference") is True


@pytest.mark.asyncio
async def test_today_same_time_uses_visit_clock(context):
    """'today same time' keeps visit hour and moves to today's calendar day."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    appt_id = str(uuid4())
    context.metadata["appointment_id"] = appt_id
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Brake Repair"
    context.metadata["upcoming_appointments"] = [
        {
            "id": appt_id,
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)
    for text in (
        "today same time",
        "today, same time",
        "same time today",
        "today at the same time",
        "Brake Repair today same time",
    ):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text
        start = result.data.entities.get("preferred_start")
        assert start, text
        assert result.data.entities.get("time_precision") == "clock", text
        assert "14:00" in start or "T14:00" in start, text
        assert result.data.entities.get("needs_time") is not True, text


@pytest.mark.asyncio
async def test_tomorrow_and_weekday_same_time_uses_visit_clock(context):
    """tomorrow/Monday/next week + same time keep visit clock on the new day."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ, parse_preferred_datetime

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    appt_id = str(uuid4())
    context.metadata["appointment_id"] = appt_id
    context.metadata["active_visit_start"] = visit_start.isoformat()
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Brake Repair"
    context.metadata["upcoming_appointments"] = [
        {
            "id": appt_id,
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    agent = IntentAgent(catalog=catalog)

    async def _assert_clock_on_day(text: str, day_prefix: str) -> None:
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text
        start = result.data.entities.get("preferred_start")
        assert start, text
        assert result.data.entities.get("time_precision") == "clock", text
        assert "14:00" in start or "T14:00" in start, text
        assert day_prefix in start, f"{text} expected day containing {day_prefix}, got {start}"
        assert result.data.entities.get("needs_time") is not True, text
        assert result.data.entities.get("same_slot_preference") is True, text

    # "now" from parse follows system date; compare day component via parser.
    for text in (
        "tomorrow same time",
        "tomorrow, same time",
        "same time tomorrow",
        "tomorrow at the same time",
        "tmrw same time",
        "Brake Repair tomorrow same time",
    ):
        day = parse_preferred_datetime(text)
        assert day.start is not None, text
        await _assert_clock_on_day(text, day.start.date().isoformat())

    for text in (
        "monday same time",
        "Monday same time",
        "on Monday same time",
        "next Monday same time",
        "Monday at the same time",
        "same time Monday",
        "same time on Monday",
        "this Monday same time",
        "Mon same time",
        "Brake Repair Monday same time",
        "Friday same time",
        "fri same time",
    ):
        day = parse_preferred_datetime(text)
        assert day.start is not None, text
        await _assert_clock_on_day(text, day.start.date().isoformat())

    for text in (
        "next week same time",
        "same time next week",
        "day after tomorrow same time",
        "the day after tomorrow same time",
    ):
        day = parse_preferred_datetime(text)
        assert day.start is not None, text
        await _assert_clock_on_day(text, day.start.date().isoformat())


@pytest.mark.asyncio
async def test_today_same_time_rebinds_after_visit_anchor_appears(context):
    """'today same time' without visit context first, then with enriched visit."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ
    from app.agents.intent.service import apply_same_slot_preference_to_entities

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    # No visit on context yet (orchestrator enriches after intent historically).
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Brake Repair"
    agent = IntentAgent(catalog=catalog)
    result = await agent.detect(_msg("today same time"), context)
    assert result.data is not None
    assert result.data.entities.get("keep_same_time") is True
    # Day preference kept, still needs clock until visit appears.
    assert result.data.entities.get("needs_time") is True

    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    appt_id = str(uuid4())
    context.metadata["appointment_id"] = appt_id
    context.metadata["active_visit_start"] = visit_start.isoformat()
    context.metadata["upcoming_appointments"] = [
        {
            "id": appt_id,
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    entities = dict(result.data.entities)
    assert apply_same_slot_preference_to_entities(
        "today same time", entities, context
    )
    start = entities.get("preferred_start")
    assert start
    assert "14:00" in start or "T14:00" in start
    assert entities.get("time_precision") == "clock"
    assert entities.get("needs_time") is not True


@pytest.mark.asyncio
async def test_same_time_uses_active_visit_start_without_upcoming(context):
    """Memory visit start alone is enough for same-time after a book-in-call."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    context.metadata["appointment_id"] = str(uuid4())
    context.metadata["active_visit_start"] = visit_start.isoformat()
    context.metadata["pending_action"] = "reschedule"
    context.metadata["pending_service"] = "Brake Repair"
    agent = IntentAgent()
    result = await agent.detect(_msg("same time"), context)
    assert result.data is not None
    start = result.data.entities.get("preferred_start")
    assert start
    assert "14:00" in start or "T14:00" in start
    result2 = await agent.detect(_msg("today same time"), context)
    assert result2.data is not None
    start2 = result2.data.entities.get("preferred_start")
    assert start2
    assert "14:00" in start2 or "T14:00" in start2
    assert result2.data.entities.get("time_precision") == "clock"


@pytest.mark.asyncio
async def test_new_service_same_time_is_reschedule_not_book(context):
    """Service-type swap + 'same time' must not fall into a fresh book."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    appt_id = str(uuid4())
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    context.metadata["appointment_id"] = appt_id
    context.metadata["active_appointment_id"] = appt_id
    context.metadata["upcoming_appointments"] = [
        {
            "id": appt_id,
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    # No pending_action — customer often names the destination + same time in one turn.
    agent = IntentAgent(catalog=catalog)
    for text in (
        "Brake Repair same time",
        "Brake Repair, same time please",
        "switch to brake repair at the same time",
        "change the service type to brake repair same time",
    ):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text
        assert result.data.entities.get("requested_service") == "Brake Repair", text
        start = result.data.entities.get("preferred_start")
        assert start, text
        assert "14:00" in start or "T14:00" in start, text
        assert result.data.entities.get("same_slot_preference") is True, text


@pytest.mark.asyncio
async def test_same_time_stt_variants(context):
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    context.metadata["pending_action"] = "reschedule"
    agent = IntentAgent(catalog=catalog)
    for text in ("same times", "sametime", "same-time"):
        result = await agent.detect(_msg(text), context)
        assert result.data is not None, text
        assert result.data.intent == CustomerIntent.RESCHEDULE, text
        assert result.data.entities.get("preferred_start"), text


@pytest.mark.asyncio
async def test_friday_same_time_combines_day_with_visit_clock(context):
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

    catalog = InMemoryServiceCatalog()
    catalog.seed_from_starter(context.shop_id)
    # Visit is Wednesday 2pm; customer says Friday same time.
    visit_start = datetime(2026, 8, 12, 14, 0, tzinfo=DEFAULT_SHOP_TZ)  # Wed
    context.metadata["upcoming_appointments"] = [
        {
            "id": str(uuid4()),
            "start": visit_start.isoformat(),
            "service_name": "Oil Change",
            "status": "booked",
        }
    ]
    context.metadata["pending_action"] = "reschedule"
    agent = IntentAgent(catalog=catalog)
    # 2026-08-03 is Monday → Friday is 2026-08-07
    result = await agent.detect(_msg("Friday same time"), context)
    assert result.data is not None
    start = result.data.entities.get("preferred_start")
    assert start
    assert result.data.entities.get("time_precision") == "clock"
    # Clock from visit (14:00); day from Friday parse (depends on "now").
    assert "14:00" in start or "T14:00" in start


@pytest.mark.asyncio
async def test_same_time_without_visit_does_not_invent_slot(context):
    """Without an appointment anchor, 'same time' is not a preferred_start."""
    agent = IntentAgent()
    result = await agent.detect(_msg("same time"), context)
    assert result.data is not None
    assert result.data.entities.get("preferred_start") is None
