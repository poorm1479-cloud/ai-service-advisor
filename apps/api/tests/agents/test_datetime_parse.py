"""Preferred datetime extraction for booking conversations."""

from __future__ import annotations

from datetime import datetime

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
