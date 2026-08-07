"""Preferred datetime extraction for booking conversations."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ, parse_preferred_datetime


def test_parse_weekday_and_time():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)  # Monday
    parsed = parse_preferred_datetime("Can I come Tuesday at 2pm?", now=now)
    assert parsed.start is not None
    assert parsed.start.weekday() == 1  # Tuesday
    assert parsed.start.hour == 14
    assert parsed.start.tzinfo == DEFAULT_SHOP_TZ
    assert parsed.end is not None
    assert parsed.end > parsed.start
    assert parsed.precision == "clock"


def test_parse_tomorrow_morning():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("tomorrow morning", now=now)
    assert parsed.start is not None
    assert parsed.start.date().isoformat() == "2026-08-04"
    assert parsed.start.hour == 9
    assert parsed.precision == "part_of_day"


def test_parse_day_only_is_window_not_chosen_time():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("Friday please", now=now)
    assert parsed.start is not None
    assert parsed.start.weekday() == 4
    assert parsed.start.hour == 8
    assert parsed.end is not None
    assert parsed.end.hour == 17
    assert parsed.precision == "day"
    assert parsed.day_explicit is True


def test_parse_time_only_marks_day_inferred():
    """Clock without a day is provisional — callers must ask for the date."""
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("3pm", now=now)
    assert parsed.start is not None
    assert parsed.start.hour == 15
    assert parsed.precision == "clock"
    assert parsed.day_explicit is False


def test_no_datetime_returns_none():
    parsed = parse_preferred_datetime("I need an oil change")
    assert parsed.start is None
    assert parsed.end is None
    assert parsed.precision == "none"


def test_ignores_years_and_phone_digits():
    parsed = parse_preferred_datetime(
        "Call me at 555-123-4567 about VIN 1HGCM82633A004352 from 2024"
    )
    assert parsed.start is None
    assert parsed.end is None


def test_parse_today_at_hour():
    """'today at 3' → today 15:00 (shop-hours afternoon heuristic)."""
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("today at 3", now=now)
    assert parsed.start is not None
    assert parsed.start.date().isoformat() == "2026-08-03"
    assert parsed.start.hour == 15
    assert parsed.precision == "clock"


def test_parse_today_oclock():
    now = datetime(2026, 8, 3, 8, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("today at 10 o'clock", now=now)
    assert parsed.start is not None
    assert parsed.start.hour == 10
    assert parsed.precision == "clock"


def test_parse_tomorrow_day_window():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("tomorrow first available", now=now)
    assert parsed.start is not None
    assert parsed.start.date().isoformat() == "2026-08-04"
    assert parsed.precision == "day"


def test_parse_morning_part_rolls_forward():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("morning first slot", now=now)
    assert parsed.start is not None
    # Time-only morning already past 10am → roll to tomorrow morning.
    assert parsed.start.date().isoformat() == "2026-08-04"
    assert parsed.start.hour == 9
    assert parsed.precision == "part_of_day"


def test_parse_today_afternoon():
    now = datetime(2026, 8, 3, 10, 0, tzinfo=DEFAULT_SHOP_TZ)
    parsed = parse_preferred_datetime("today afternoon", now=now)
    assert parsed.start is not None
    assert parsed.start.date().isoformat() == "2026-08-03"
    assert parsed.start.hour == 13
    assert parsed.precision == "part_of_day"


def test_parse_same_slot_preference_phrases():
    from app.agents.intent.datetime_parse import parse_same_slot_preference

    both = parse_same_slot_preference("same day and time please")
    assert both is not None
    assert both.keep_day and both.keep_time

    same_time = parse_same_slot_preference("same time")
    assert same_time is not None
    assert same_time.keep_time
    assert not same_time.keep_day

    same_day = parse_same_slot_preference("keep the same day")
    assert same_day is not None
    # "keep the same" is full-slot; "keep the same day" matches both first.
    assert same_day.keep_day

    keep = parse_same_slot_preference("keep it the same")
    assert keep is not None
    assert keep.keep_day and keep.keep_time

    assert parse_same_slot_preference("I need an oil change") is None
    assert parse_same_slot_preference("3pm") is None


def test_relative_and_weekday_day_phrases():
    """tomorrow / Monday abbreviations / next week day resolution."""
    from datetime import datetime

    from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ, parse_preferred_datetime

    now = datetime(2026, 8, 7, 10, 0, tzinfo=DEFAULT_SHOP_TZ)  # Friday

    # tomorrow + typos
    for text in ("tomorrow", "tmrw morning", "tomorow at 2pm"):
        p = parse_preferred_datetime(text, now=now)
        assert p.start is not None, text
        assert p.start.date().isoformat() == "2026-08-08", text
        assert p.day_explicit, text

    # day after tomorrow (must not collapse to tomorrow)
    p = parse_preferred_datetime("day after tomorrow same time", now=now)
    assert p.start is not None
    assert p.start.date().isoformat() == "2026-08-09"

    # next week ≈ +7 days from today
    p = parse_preferred_datetime("next week same time", now=now)
    assert p.start is not None
    assert p.start.date().isoformat() == "2026-08-14"
    assert p.day_explicit

    # full weekday + mon abbreviation → next Monday (2026-08-10)
    for text in ("monday same time", "Mon same time", "next Monday", "this Monday"):
        p = parse_preferred_datetime(text, now=now)
        assert p.start is not None, text
        assert p.start.date().isoformat() == "2026-08-10", text
        assert p.day_explicit, text

    # tue abbreviation
    p = parse_preferred_datetime("tue same time", now=now)
    assert p.start is not None
    assert p.start.date().isoformat() == "2026-08-11"


@pytest.mark.parametrize(
    "text",
    [
        "same time",
        "the same time",
        "same times",
        "sametime",
        "same-time",
        "same slot",
        "same timing",
        "keep the time",
        "keep the same time",
        "keep my current time",
        "leave the time as is",
        "don't change the time",
        "do not change the time",
        "no need to change the time",
        "time stays the same",
        "the time is fine",
        "that time works",
        "still the same time",
        "prefer the same time",
        "want same time",
        "not a different time",
        "no new time needed",
        "no time change",
        "reuse the time",
        "use the existing time",
        "stick with the same time",
        "hold the time",
        "original time",
        "existing time",
        "previous time",
        "same hour",
        "at the same o'clock",
        "time-wise same",
        "don't need a new time",
        "maintain the same time",
        "time unchanged",
        "keep timing the same",
        "tomorrow same time",
        "monday same time",
        "same time Monday",
        "fri same time",
        "next week same time",
    ],
)
def test_same_time_synonyms(text):
    from app.agents.intent.datetime_parse import parse_same_slot_preference

    pref = parse_same_slot_preference(text)
    assert pref is not None, text
    assert pref.keep_time, text


@pytest.mark.parametrize(
    "text",
    [
        "same day and time",
        "same time and day",
        "same date/time",
        "same datetime",
        "keep it the same",
        "keep everything the same",
        "leave it as is",
        "as before",
        "like before",
        "as previously",
        "as it was",
        "don't change anything",
        "same appointment",
        "same visit",
        "same slot",
    ],
)
def test_same_slot_both_synonyms(text):
    from app.agents.intent.datetime_parse import parse_same_slot_preference

    pref = parse_same_slot_preference(text)
    assert pref is not None, text
    assert pref.keep_day and pref.keep_time, text


@pytest.mark.parametrize(
    "text",
    [
        "I need an oil change",
        "3pm",
        "what time works",
        "change the time",
        "reschedule please",
        "Friday morning",
    ],
)
def test_same_slot_non_matches(text):
    from app.agents.intent.datetime_parse import parse_same_slot_preference

    assert parse_same_slot_preference(text) is None, text
