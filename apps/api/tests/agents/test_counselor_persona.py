"""Counselor spoken-name helpers."""

from app.agents.counselor.persona import (
    ask_purpose,
    ask_service,
    first_reply_prefix,
    greeting,
    is_purpose_question,
    looks_like_booking_desire,
    spoken_first_name,
    summarize_booking_confirm,
    time_unavailable,
)


def test_time_unavailable_asks_for_another():
    body = time_unavailable(
        __import__("datetime").datetime(2026, 8, 5, 14, 0),
        customer_name="Alex",
    )
    assert "isn't available" in body.lower()
    assert "other" in body.lower()
    assert "Alex" in body


def test_format_when_uses_shop_timezone():
    from datetime import datetime, timezone

    from app.agents.counselor.persona import format_when, format_when_range

    # 15:00 UTC in August = 08:00 America/Los_Angeles
    utc = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    assert format_when(utc) == "Wednesday at 8:00 AM"
    end = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
    assert format_when_range(utc, end) == "Wednesday from 8:00 AM to 9:00 AM"


def test_offer_slots_spoken_uses_from_to_windows():
    from datetime import datetime, timezone

    from app.agents.counselor.persona import offer_slots_spoken

    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
    body = offer_slots_spoken([(start, end)], customer_name="Alex")
    assert "from 8:00 AM to 9:00 AM" in body
    assert "I've got openings" in body
    assert "go ahead" not in body.lower()
    assert "going" not in body.lower()


def test_booking_confirm_omits_go_ahead():
    body = summarize_booking_confirm(
        customer_name="Alex",
        service_name="Oil Change",
        when=__import__("datetime").datetime(2026, 8, 5, 14, 0),
    )
    assert "should i book that" in body.lower()
    assert "go ahead" not in body.lower()
    assert "going" not in body.lower()


def test_spoken_first_name_skips_unknown_placeholders():
    assert spoken_first_name(None) == ""
    assert spoken_first_name("") == ""
    assert spoken_first_name("Unknown") == ""
    assert spoken_first_name("Unknown Customer") == ""
    assert spoken_first_name("unknown customer") == ""
    assert spoken_first_name("Going") == ""
    assert spoken_first_name("gonna") == ""
    assert spoken_first_name("Alex Rivera") == "Alex"
    assert "Going" not in greeting(shop_name="Main Street Auto", customer_name="Going")
    assert greeting(shop_name="Main Street Auto", customer_name="Going").startswith(
        "Hello, this is Main Street Auto"
    )
    assert "Going" not in ask_service(customer_name="Going")
    assert ask_service(customer_name="Going") == "what service do you need?"
    body = summarize_booking_confirm(
        customer_name="Going",
        service_name="Oil Change",
        when=None,
    )
    assert "Going" not in body
    assert body.startswith("book you for Oil Change")


def test_sanitize_spoken_reply_strips_going_address():
    from app.agents.counselor.persona import sanitize_spoken_reply

    assert sanitize_spoken_reply("Going, what service do you need?") == (
        "what service do you need?"
    )
    assert sanitize_spoken_reply("Hello Going, this is Main Street Auto. ") == (
        "Hello, this is Main Street Auto."
    )
    assert sanitize_spoken_reply("Alex, what day works?") == "Alex, what day works?"


def test_ask_name_for_new_customers():
    from app.agents.counselor.persona import ask_name, is_name_question, needs_customer_name

    assert needs_customer_name("Unknown Customer")
    assert needs_customer_name(None)
    assert not needs_customer_name("Alex")
    ask = ask_name()
    assert "name" in ask.lower()
    assert is_name_question(ask)
    assert is_name_question("what's your name so I can put the booking under you?")


def test_replies_omit_unknown_name():
    assert ask_service(customer_name="Unknown Customer") == "what service do you need?"
    assert "Unknown" not in greeting(shop_name="Main Street Auto", customer_name="Unknown")
    assert greeting(shop_name="Main Street Auto", customer_name="Unknown").startswith(
        "Hello, this is Main Street Auto"
    )
    body = summarize_booking_confirm(
        customer_name="Unknown Customer",
        service_name="Oil Change",
        when=None,
    )
    assert body.startswith("book you for Oil Change")
    assert "Unknown" not in body


def test_greeting_introduces_shop_and_asks_purpose():
    text = greeting(shop_name="Main Street Auto")
    assert text.startswith("Hello, this is Main Street Auto")
    assert "what can i help you with" in text.lower()
    assert ask_purpose() == "what can I help you with?"
    assert first_reply_prefix(shop_name="Main Street Auto") == "Hello, this is Main Street Auto. "
    assert is_purpose_question(ask_purpose())
    assert looks_like_booking_desire("I want to make a reservation")
    assert looks_like_booking_desire("I'd like to book an appointment")
    assert not looks_like_booking_desire("hello there")
    # Time-change / cancel must not look like a new booking (would ask for service).
    assert not looks_like_booking_desire("Can I change my appointment time?")
    assert not looks_like_booking_desire("I want to change my appointment")
    assert not looks_like_booking_desire("Please reschedule my appointment")
    assert not looks_like_booking_desire("Cancel my appointment")
    assert not looks_like_booking_desire("move my appointment to Friday")
    assert not looks_like_booking_desire("I need an appointment time change")
    assert not looks_like_booking_desire("reservation time change")
    from app.agents.counselor.persona import looks_like_reschedule_desire

    assert looks_like_reschedule_desire("I need an appointment time change")
    assert looks_like_reschedule_desire("reservation time change")
    assert looks_like_reschedule_desire("I want to change my time")
    # Oil change booking must not look like a time-change ask.
    assert not looks_like_reschedule_desire("I need an oil change appointment")
    assert looks_like_booking_desire("I need an oil change appointment")
