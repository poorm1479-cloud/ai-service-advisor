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
async def test_yes_sets_booking_confirmed(context):
    agent = IntentAgent()
    result = await agent.detect(_msg("YES"), context)
    assert result.data is not None
    assert result.data.intent == CustomerIntent.BOOK_APPOINTMENT
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
