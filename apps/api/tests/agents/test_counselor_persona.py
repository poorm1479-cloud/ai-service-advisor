"""Counselor spoken-name helpers."""

from app.agents.counselor.persona import (
    ask_date,
    ask_purpose,
    ask_service,
    ask_time,
    first_reply_prefix,
    greeting,
    is_anything_else_question,
    is_purpose_question,
    looks_like_booking_desire,
    looks_like_farewell,
    looks_like_soft_no,
    spoken_first_name,
    summarize_booking_confirm,
    summarize_done,
    time_unavailable,
)


def test_ask_time_with_known_day_asks_only_time():
    from datetime import datetime, timezone

    day = datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc)  # Friday in LA
    body = ask_time(customer_name="Alex", service_name="Oil Change", known_day=day)
    assert "Alex" in body
    assert "time" in body.lower()
    assert "Friday" in body
    # Should not re-ask for both day and time equally
    assert "day and time" not in body.lower()


def test_ask_date_with_known_time_asks_only_day():
    from datetime import datetime, timezone

    when = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)  # 8am LA
    body = ask_date(customer_name="Alex", service_name="Oil Change", known_time=when)
    assert "Alex" in body
    assert "day" in body.lower()
    assert "8:00 AM" in body
    assert "day and time" not in body.lower()


def test_time_unavailable_asks_for_another():
    body = time_unavailable(
        __import__("datetime").datetime(2026, 8, 5, 14, 0),
        customer_name="Alex",
    )
    assert "isn't available" in body.lower()
    assert "other" in body.lower()
    assert "Alex" in body


def test_time_unavailable_reasks_only_broken_half():
    from datetime import datetime, timezone

    # 14:00 naive → shop TZ formatting still works via replace
    when = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)  # 8am LA Wednesday
    date_only = time_unavailable(when, ask="date")
    assert "day" in date_only.lower()
    assert "other day" in date_only.lower()
    assert "day or time" not in date_only.lower()

    time_only = time_unavailable(when, ask="time")
    assert "time" in time_only.lower()
    assert "other time" in time_only.lower()
    assert "day or time" not in time_only.lower()

    closed = time_unavailable(when, ask="date", day_only=True)
    assert "other day" in closed.lower()
    assert "8:00" not in closed  # no invented clock on day-only closed


def test_format_when_uses_shop_timezone():
    from datetime import datetime, timezone

    from app.agents.counselor.persona import format_duration, format_when, format_when_range

    # 15:00 UTC in August = 08:00 America/Los_Angeles
    utc = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    assert format_when(utc) == "Wednesday at 8:00 AM"
    end = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
    assert format_when_range(utc, end) == "Wednesday from 8:00 AM to 9:00 AM"
    half = datetime(2026, 8, 5, 15, 30, tzinfo=timezone.utc)
    assert format_when_range(utc, half) == "Wednesday from 8:00 AM to 8:30 AM"
    ninety = datetime(2026, 8, 5, 16, 30, tzinfo=timezone.utc)
    assert format_duration(utc, ninety) == "1 hour 30 minutes"


def test_offer_slots_spoken_uses_from_to_windows():
    from datetime import datetime, timezone

    from app.agents.counselor.persona import offer_slots_spoken

    start = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
    body = offer_slots_spoken([(start, end)], customer_name="Alex")
    assert "from 8:00 AM to 9:00 AM" in body
    assert "for 1 hour" not in body
    assert "minute" not in body.lower()
    assert "I've got a few openings" in body
    assert "go ahead" not in body.lower()
    assert "going" not in body.lower()


def test_offer_slots_spoken_merges_contiguous_microslots():
    """Half-hour bookable slots become one continuous window (8–9, not 8–8:30 + 8:30–9)."""
    from datetime import datetime, timedelta, timezone

    from app.agents.counselor.persona import merge_contiguous_windows, offer_slots_spoken

    # 08:00–08:30 and 08:30–09:00 LA (= 15:00–16:00 UTC)
    t0 = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    micro = [
        (t0, t0 + timedelta(minutes=30)),
        (t0 + timedelta(minutes=30), t0 + timedelta(minutes=60)),
    ]
    merged = merge_contiguous_windows(micro)
    assert len(merged) == 1
    assert merged[0] == (t0, t0 + timedelta(minutes=60))

    body = offer_slots_spoken(micro, customer_name="Alex")
    assert "from 8:00 AM to 9:00 AM" in body
    assert "for 1 hour" not in body
    assert "8:30 AM" not in body  # not spoken as two micro-slots

    # Gap between blocks → two windows
    gap = [
        (t0, t0 + timedelta(minutes=30)),
        (t0 + timedelta(minutes=90), t0 + timedelta(minutes=120)),
    ]
    assert len(merge_contiguous_windows(gap)) == 2
    body_gap = offer_slots_spoken(gap)
    assert "from 8:00 AM to 8:30 AM" in body_gap
    assert "from 9:30 AM to 10:00 AM" in body_gap
    assert "for 30 minutes" not in body_gap


def test_booking_confirm_omits_go_ahead():
    body = summarize_booking_confirm(
        customer_name="Alex",
        service_name="Oil Change",
        when=__import__("datetime").datetime(2026, 8, 5, 14, 0),
    )
    assert "shall i book that" in body.lower()
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
    assert ask_service(customer_name="Going") == "sure — what service can I help you with?"
    body = summarize_booking_confirm(
        customer_name="Going",
        service_name="Oil Change",
        when=None,
    )
    assert "Going" not in body
    assert body.startswith("I can book you for Oil Change")


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
    assert is_name_question("may I have your name so I can put the booking under you?")


def test_replies_omit_unknown_name():
    assert ask_service(customer_name="Unknown Customer") == (
        "sure — what service can I help you with?"
    )
    assert "Unknown" not in greeting(shop_name="Main Street Auto", customer_name="Unknown")
    assert greeting(shop_name="Main Street Auto", customer_name="Unknown").startswith(
        "Hello, this is Main Street Auto"
    )
    body = summarize_booking_confirm(
        customer_name="Unknown Customer",
        service_name="Oil Change",
        when=None,
    )
    assert body.startswith("I can book you for Oil Change")
    assert "Unknown" not in body


def test_greeting_introduces_shop_and_asks_purpose():
    text = greeting(shop_name="Main Street Auto")
    assert text.startswith("Hello, this is Main Street Auto")
    assert "how can i help you today" in text.lower()
    assert ask_purpose() == "how can I help you today?"
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
    assert looks_like_reschedule_desire("I need to reschedule")
    assert looks_like_reschedule_desire("Push my appointment back")
    assert looks_like_reschedule_desire("I can't make it")
    assert looks_like_reschedule_desire("Can I come another day?")
    assert looks_like_reschedule_desire("Update my appointment")
    assert looks_like_reschedule_desire("Change the date")
    assert looks_like_reschedule_desire("reset")
    assert looks_like_reschedule_desire("Reset my appointment")
    assert looks_like_reschedule_desire("I need to reset")
    assert looks_like_reschedule_desire("replace")
    assert looks_like_reschedule_desire("Replace my appointment")
    assert looks_like_reschedule_desire("I need to replace")
    assert looks_like_reschedule_desire("redo my booking")
    assert looks_like_reschedule_desire("postpone my visit")
    assert looks_like_reschedule_desire("change the service type")
    assert looks_like_reschedule_desire("Please change the service type to brake repair")
    # Oil change booking must not look like a time-change ask.
    assert not looks_like_reschedule_desire("I need an oil change appointment")
    assert looks_like_booking_desire("I need an oil change appointment")

    from app.agents.intent.reschedule_text import looks_like_service_type_change
    from app.agents.counselor.persona import ask_replacement_service

    service_type_synonyms = [
        "change the service type",
        "I want to change the service type",
        "update the service type to brakes",
        "swap the service",
        "switch services",
        "I need a different service",
        "I booked the wrong service",
        "not the right service",
        "change what I booked",
        "change the job",
        "revise the repair type",
        "go with a different service",
        "make it a different service",
        "switch to a different service",
        "change the service on my appointment",
        "I want something else done",
        "correct my service type",
        "service swap",
        "I have the wrong job on the booking",
        "Can I change what service I booked?",
        "update my type of service",
        "actually I need a different repair",
    ]
    for phrase in service_type_synonyms:
        assert looks_like_service_type_change(phrase), phrase
        assert looks_like_reschedule_desire(phrase), phrase

    # Time-only changes must not look like a service-type swap.
    for phrase in (
        "Can I change my appointment time?",
        "I want to change the date",
        "reschedule for Friday",
        "Push my appointment back",
        # "service time" is a clock move, not a job swap (STT / casual phrasing)
        "change the service time",
        "I want to change the service time",
        "change my service time",
        "update the service time",
        "modify the service time",
        "change service schedule",
        "service time change",
        "change my service appointment time",
    ):
        assert not looks_like_service_type_change(phrase), phrase

    # Appointment + service object = job swap (not a bare time move).
    for phrase in (
        "service change",
        "service kind change",
        "change my appointment service",
        "change the appointment service type",
        "not the service I wanted",
        "kind of service change",
        # Compound service + time change (spoken synonyms)
        "Change both the service type and the time",
        "change the service type and the appointment time",
        "I want to change both the service and the time",
        "change time and service type",
        "service and time change",
        "Can I change both the service and the date?",
        "I'd like to update the service type as well as the time",
        "switch the job and the day",
        "modify service plus time",
        "change the service type along with the schedule",
        "need a different service and a different time",
        "I need a new service and a new time",
        "change what and when",
        "update service and when",
        "reschedule with a different service and time",
        "both the service and the time",
        "both time and service type",
        "change the time and the service too",
        "not just the time, the service too",
        "not only the service but also the day",
        "change the whole appointment",
        "redo the entire booking",
        "change it all",
        "swap service and time",
        "alter the repair type and the day",
        "please change both service kind and date",
        "time and service swap",
        "service and time update",
        "want a different job and another day",
    ):
        assert looks_like_service_type_change(phrase), phrase
        assert looks_like_reschedule_desire(phrase), phrase

    assert "instead of Oil Change" in ask_replacement_service(
        current_service="Oil Change"
    )


def test_summarize_done_keep_open_offers_more_help():
    body = summarize_done(
        action="book",
        customer_name="Alex",
        service_name="Oil Change",
        when=__import__("datetime").datetime(2026, 8, 5, 14, 0),
        keep_open=True,
    )
    assert "booked" in body.lower()
    assert "anything else" in body.lower()
    assert "take care" not in body.lower()

    closed = summarize_done(action="book", service_name="Oil Change", keep_open=False)
    assert "take care" in closed.lower()


def test_redirect_to_service_topic_is_kind_and_scoped():
    from app.agents.counselor.persona import looks_like_off_topic, redirect_to_service_topic

    body = redirect_to_service_topic()
    assert "vehicle service" in body.lower() or "shop" in body.lower()
    assert "book" in body.lower()
    assert "Going" not in redirect_to_service_topic(customer_name="Going")
    named = redirect_to_service_topic(customer_name="Alex")
    assert named.startswith("Alex,")
    assert "vehicle" in named.lower() or "shop" in named.lower()

    assert looks_like_off_topic("What's the weather like today? Tell me a joke.")
    assert looks_like_off_topic("Who won the game last night?")
    assert not looks_like_off_topic("I need to book an oil change")
    assert not looks_like_off_topic("Can I change my appointment?")
    assert not looks_like_off_topic("What times are available tomorrow?")


def test_farewell_and_soft_no_detection():
    assert looks_like_farewell("goodbye")
    assert looks_like_farewell("that's all")
    assert looks_like_farewell("nothing else")
    assert not looks_like_farewell("nope")  # not bare decline mid-call
    assert not looks_like_farewell("I need an oil change")
    assert looks_like_soft_no("no")
    assert looks_like_soft_no("nope")
    assert looks_like_soft_no("No, thank you")
    assert looks_like_soft_no("No, I'm good")
    assert looks_like_soft_no("I'm all set")
    assert looks_like_soft_no("nothing more")
    assert looks_like_soft_no("thanks")
    assert is_anything_else_question("Is there anything else I can help you with?")
    assert is_anything_else_question("Anything else I can help with?")
    assert not is_anything_else_question("Shall I book that for you?")

    from app.agents.counselor.persona import wants_to_end_after_offer

    assert wants_to_end_after_offer(
        "No, thank you",
        pending_question="Is there anything else I can help you with?",
    )
    assert wants_to_end_after_offer(
        "no",
        last_assistant_text=(
            "You're booked for Oil Change. Is there anything else I can help you with?"
        ),
    )
    assert not wants_to_end_after_offer(
        "no",
        pending_question="Shall I book that for you?",
    )