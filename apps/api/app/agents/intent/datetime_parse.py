"""Lightweight natural-language datetime extraction for booking chats.

Heuristic only — no LLM. Returns timezone-aware datetimes in the shop TZ
(default America/Los_Angeles) so they align with AppointmentIntelligence slots.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple
from zoneinfo import ZoneInfo

# Matches shop scheduling / availability engines in this project.
DEFAULT_SHOP_TZ = ZoneInfo("America/Los_Angeles")

TimePrecision = Literal["none", "day", "part_of_day", "clock"]


class PreferredDatetime(NamedTuple):
    start: datetime | None
    end: datetime | None
    precision: TimePrecision = "none"
    # False when only a clock / part-of-day was said (day was inferred).
    day_explicit: bool = True


class SameSlotPreference(NamedTuple):
    """Customer wants to reuse the existing visit day and/or clock time."""

    keep_day: bool
    keep_time: bool


# Shared tokens for keep-slot phrasing (spoken + STT-friendly variants).
_SLOT_TIME = (
    r"(?:times?|slot|timing|hour|"
    r"appointment\s+times?|visit\s+times?|booking\s+times?|"
    r"scheduled\s+times?|current\s+times?)"
)
_SLOT_DAY = r"(?:day|date|calendar\s+day)"
_KEEP = (
    r"(?:keep|leave|retain|hold|holding|"
    r"stick\s+with|stay\s+with|stick\s+to|go\s+with)"
)
_NO_CHANGE = (
    r"(?:don'?t|do\s+not|no\s+need\s+to|need\s+not|no\s+reason\s+to)\s+"
    r"(?:change|move|shift|update|alter|adjust|touch|edit|modify)"
)
_UNCHANGED = (
    r"(?:unchanged|unaltered|the\s+same|"
    r"as\s+(?:is|before|previously|it\s+(?:is|was)))"
)
_SAME_ADJ = r"(?:same|identical|existing|original|previous|current|old)"

# Full slot keep ("same day and time", "keep it the same", "as before").
_SAME_BOTH = re.compile(
    r"\b("
    # same day and time / datetime
    r"same\s+(?:day|date)\s+and\s+(?:the\s+)?(?:time|slot|timing)|"
    r"same\s+(?:time|slot|timing)\s+and\s+(?:the\s+)?(?:day|date)|"
    r"same\s+(?:day|date)\s+(?:time|slot)|"
    r"same\s+(?:date\s*/*\s*time|datetime|date-?time)|"
    r"same\s+(?:appointment|visit|booking|reservation|slot)\b|"
    r"(?:exactly\s+)?the\s+same\s+(?:appointment|visit|booking|slot|datetime)|"
    # keep / leave everything as-is
    rf"{_KEEP}\s+(?:everything|it|that|this|all)\s+{_UNCHANGED}|"
    rf"{_KEEP}\s+(?:everything|it)\b|"
    r"keep\s+(?:the\s+)?same\b|"
    r"(?:leave|let)\s+(?:it|that|everything)\s+(?:be\s+)?{_UNCHANGED}|"
    r"(?:stay|stays|staying|remain|remains|remaining)\s+{_UNCHANGED}|"
    r"(?:as|like|just\s+like)\s+(?:before|previously|the\s+original)|"
    r"as\s+it\s+(?:is|was)\b|"
    r"as\s+is\b|"
    r"like\s+it\s+was\b|"
    r"original\s+(?:time\s+and\s+day|day\s+and\s+time|datetime)|"
    r"without\s+(?:changing|moving)\s+(?:the\s+)?"
    r"(?:time\s+or\s+day|day\s+or\s+time|date\s+or\s+time|time\s+or\s+date)|"
    r"don'?t\s+(?:change|move|touch)\s+(?:anything|either)|"
    r"no\s+(?:need\s+to\s+)?change\s+(?:the\s+)?(?:day|date)\s+or\s+"
    r"(?:the\s+)?(?:time|slot)|"
    r"no\s+(?:need\s+to\s+)?change\s+(?:the\s+)?(?:time|slot)\s+or\s+"
    r"(?:the\s+)?(?:day|date)|"
    r"nothing\s+(?:changes|to\s+change)\s+(?:on\s+)?(?:the\s+)?(?:day|time|schedule)"
    r")\b",
    re.I,
)
# Clock-only keep ("same time", "keep the time", spoken/STT variants).
_SAME_TIME = re.compile(
    r"\b("
    # same / identical / existing clock
    rf"(?:the\s+)?{_SAME_ADJ}\s+{_SLOT_TIME}|"
    rf"(?:my\s+|the\s+|that\s+)?(?:current|original|existing|previous|old)\s+"
    rf"{_SLOT_TIME}|"
    rf"(?:at\s+)?(?:the\s+)?same\s+(?:hour|o'?clock)\b|"
    r"same\s+(?:clock\s+)?times?\b|"
    r"same[- ]?times?\b|"
    r"sametime\b|"
    r"same\s+timing\b|"
    # keep / leave / stick with time
    rf"{_KEEP}\s+(?:the\s+|my\s+|that\s+)?"
    rf"(?:same\s+|current\s+|original\s+|existing\s+|previous\s+|old\s+)?"
    rf"{_SLOT_TIME}|"
    rf"{_KEEP}\s+(?:the\s+)?(?:same\s+)?hour\b|"
    rf"{_KEEP}\s+timing\s+(?:{_UNCHANGED})?|"
    # don't change time
    rf"{_NO_CHANGE}\s+(?:the\s+|my\s+|that\s+)?{_SLOT_TIME}|"
    rf"{_NO_CHANGE}\s+(?:the\s+)?hour\b|"
    # leave time as is / time stays the same
    rf"leave\s+(?:the\s+|my\s+)?{_SLOT_TIME}\s+(?:{_UNCHANGED}|alone)|"
    rf"(?:the\s+|my\s+|that\s+){_SLOT_TIME}\s+(?:can\s+)?"
    rf"(?:stay|stays|remain|remains|be)\s+{_UNCHANGED}|"
    rf"(?:the\s+|my\s+|that\s+){_SLOT_TIME}\s+(?:is\s+)?"
    rf"(?:fine|ok|okay|good)(?:\s+as\s+(?:is|before))?|"
    # casual / STT
    r"(?:the\s+|my\s+)?time\s+(?:doesn'?t|does\s+not)\s+(?:need\s+to\s+)?change|"
    r"no\s+(?:new\s+)?time\s+(?:needed|change)|"
    r"no\s+time\s+change|"
    r"time[- ]wise\s+(?:no\s+change|unchanged|same|fine|ok|okay)|"
    r"don'?t\s+(?:need\s+(?:a\s+)?new\s+time|"
    r"worry\s+about\s+(?:the\s+)?time)|"
    r"(?:reuse|re-?use|use)\s+(?:the\s+)?"
    rf"(?:same\s+|existing\s+|original\s+|current\s+|previous\s+)?{_SLOT_TIME}|"
    r"(?:hold|holding)\s+(?:the\s+)?(?:same\s+)?time|"
    r"that\s+(?:same\s+)?time\s+(?:is\s+)?(?:fine|ok|okay|good|works)|"
    r"still\s+(?:the\s+)?same\s+(?:time|slot|timing)|"
    r"(?:prefer|want|like)\s+(?:to\s+)?(?:keep\s+)?"
    r"(?:the\s+)?same\s+(?:time|slot|timing)|"
    # Day + keep-time compounds (spoken order either way)
    r"(?:today|tomorrow|tonight|tmrw|mon(?:day)?|tue(?:s(?:day)?)?|"
    r"wed(?:nes(?:day)?)?|thu(?:rs(?:day)?)?|fri(?:day)?|"
    r"sat(?:urday)?|sun(?:day)?|next\s+week)\s*"
    r"[,.]?\s*(?:at\s+)?(?:the\s+)?same\s+(?:time|slot|timing|hour)\b|"
    r"(?:at\s+)?(?:the\s+)?same\s+(?:time|slot|timing|hour)\s+"
    r"(?:(?:on|for)\s+)?(?:today|tomorrow|tonight|tmrw|"
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nes(?:day)?)?|"
    r"thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|"
    r"next\s+week)\b|"
    r"not\s+(?:a\s+)?(?:new|different)\s+(?:time|slot)|"
    r"(?:no|without\s+a)\s+(?:time|schedule)\s+change|"
    r"time\s+stays|"
    r"unchanged\s+time|"
    r"time\s+unchanged|"
    r"(?:maintain|maintaining)\s+(?:the\s+)?(?:same\s+)?time|"
    r"(?:don'?t|do\s+not)\s+(?:reschedule|re-?schedule)\s+the\s+time|"
    r"clock\s+stays|"
    r"same\s+clock"
    r")\b",
    re.I,
)
# Day-only keep ("same day", "keep the date").
_SAME_DAY = re.compile(
    r"\b("
    rf"(?:the\s+)?{_SAME_ADJ}\s+{_SLOT_DAY}|"
    rf"(?:my\s+|the\s+|that\s+)?(?:current|original|existing|previous|old)\s+"
    rf"{_SLOT_DAY}|"
    rf"{_KEEP}\s+(?:the\s+|my\s+|that\s+)?"
    rf"(?:same\s+|current\s+|original\s+|existing\s+|previous\s+|old\s+)?"
    rf"{_SLOT_DAY}|"
    rf"{_NO_CHANGE}\s+(?:the\s+|my\s+|that\s+)?{_SLOT_DAY}|"
    rf"leave\s+(?:the\s+|my\s+)?{_SLOT_DAY}\s+(?:{_UNCHANGED}|alone)|"
    rf"(?:the\s+|my\s+|that\s+){_SLOT_DAY}\s+(?:can\s+)?"
    rf"(?:stay|stays|remain|remains|be)\s+{_UNCHANGED}|"
    r"day[- ]wise\s+(?:no\s+change|unchanged|same|fine|ok|okay)|"
    r"date[- ]wise\s+(?:no\s+change|unchanged|same|fine|ok|okay)|"
    r"(?:reuse|re-?use|use)\s+(?:the\s+)?"
    rf"(?:same\s+|existing\s+|original\s+|current\s+|previous\s+)?{_SLOT_DAY}|"
    r"still\s+(?:the\s+)?same\s+(?:day|date)|"
    r"(?:prefer|want|like)\s+(?:to\s+)?(?:keep\s+)?"
    r"(?:the\s+)?same\s+(?:day|date)|"
    r"not\s+(?:a\s+)?(?:new|different)\s+(?:day|date)|"
    r"no\s+(?:day|date)\s+change|"
    r"(?:day|date)\s+(?:stays|unchanged)|"
    r"unchanged\s+(?:day|date)|"
    r"(?:maintain|maintaining)\s+(?:the\s+)?(?:same\s+)?(?:day|date)"
    r")\b",
    re.I,
)


def parse_same_slot_preference(text: str) -> SameSlotPreference | None:
    """Detect 'same time' / keep-slot phrasing (needs an existing visit anchor)."""
    if not text or not text.strip():
        return None
    if _SAME_BOTH.search(text):
        return SameSlotPreference(keep_day=True, keep_time=True)
    keep_time = bool(_SAME_TIME.search(text))
    keep_day = bool(_SAME_DAY.search(text))
    if not keep_day and not keep_time:
        return None
    return SameSlotPreference(keep_day=keep_day, keep_time=keep_time)


def combine_day_and_clock(day_source: datetime, clock_source: datetime) -> datetime:
    """Use calendar day of day_source with clock hour/minute of clock_source."""
    day_local = (
        day_source.astimezone(DEFAULT_SHOP_TZ)
        if day_source.tzinfo
        else day_source.replace(tzinfo=DEFAULT_SHOP_TZ)
    )
    clock_local = (
        clock_source.astimezone(DEFAULT_SHOP_TZ)
        if clock_source.tzinfo
        else clock_source.replace(tzinfo=DEFAULT_SHOP_TZ)
    )
    return day_local.replace(
        hour=clock_local.hour,
        minute=clock_local.minute,
        second=0,
        microsecond=0,
    )


_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    # Spoken / STT abbreviations
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "weds": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

_TIME_OF_DAY = {
    "morning": (9, 0),
    "afternoon": (13, 0),
    "evening": (16, 0),
    "noon": (12, 0),
}

_CLOCK = re.compile(
    r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?\b",
    re.I,
)
# "3 o'clock", "3 oclock"
_OCLOCK = re.compile(r"\b(?P<h>\d{1,2})\s*o'?clock\b", re.I)
_WEEKDAY = re.compile(
    r"\b(?P<mod>(?:next|this|coming)\s+)?"
    r"(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tues?|weds?|thurs?|thur|fri|sat|sun)\b",
    re.I,
)
_RELATIVE_DAY = re.compile(
    r"\b("
    r"day\s+after\s+tomorrow|"
    r"the\s+day\s+after\s+tomorrow|"
    r"today|tomorrow|tonight|"
    # STT slips for tomorrow
    r"tmrw|tmorrow|tomorow|tommorrow|tommorow|"
    r"next\s+week|"
    r"a\s+week\s+from\s+(?:now|today)|"
    r"in\s+a\s+week"
    r")\b",
    re.I,
)
_PART_OF_DAY = re.compile(
    r"\b(morning|afternoon|evening|noon)\b",
    re.I,
)


def parse_preferred_datetime(
    text: str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | timezone = DEFAULT_SHOP_TZ,
) -> PreferredDatetime:
    """Extract preferred window + how specific the customer was about clock time.

    Day-only cues ("Friday", "tomorrow") return a shop-day window with
    precision="day" — callers must offer slots / ask for a time, not invent one.
    """
    if not text or not text.strip():
        return PreferredDatetime(None, None, "none")

    base = now or datetime.now(tz)
    if base.tzinfo is None:
        base = base.replace(tzinfo=tz)
    else:
        base = base.astimezone(tz)

    day = _parse_day(text, base)
    hour, minute, has_clock = _parse_clock(text)
    part = _PART_OF_DAY.search(text)

    if day is None and not has_clock and part is None:
        return PreferredDatetime(None, None, "none", True)

    if day is None:
        # Time-only: provisional day (today if still ahead, else tomorrow).
        # Callers must ask for an explicit day before confirming a booking.
        candidate = base.replace(hour=0, minute=0, second=0, microsecond=0)
        if has_clock:
            start = candidate.replace(hour=hour, minute=minute)
            precision: TimePrecision = "clock"
            end = start + timedelta(hours=1)
        else:
            token = part.group(0) if part else "morning"
            h, m = _part_of_day_hours(token)
            start = candidate.replace(hour=h, minute=m)
            precision = "part_of_day"
            end = start + timedelta(hours=_part_of_day_span(token))
        if start <= base:
            delta = timedelta(days=1)
            start = start + delta
            end = end + delta
        return PreferredDatetime(start, end, precision, day_explicit=False)

    if has_clock:
        start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        return PreferredDatetime(start, start + timedelta(hours=1), "clock", True)

    if part is not None:
        h, m = _part_of_day_hours(part.group(0))
        start = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
        span = _part_of_day_span(part.group(0))
        return PreferredDatetime(
            start, start + timedelta(hours=span), "part_of_day", True
        )

    # Day only — window for filtering openings; do not treat 08:00 as chosen.
    start = datetime(day.year, day.month, day.day, 8, 0, tzinfo=tz)
    end = datetime(day.year, day.month, day.day, 17, 0, tzinfo=tz)
    return PreferredDatetime(start, end, "day", True)


def _part_of_day_hours(token: str) -> tuple[int, int]:
    key = (token or "").strip().lower()
    if key in _TIME_OF_DAY:
        return _TIME_OF_DAY[key]
    return 9, 0


def _part_of_day_span(token: str) -> int:
    """Hours covered by a soft part-of-day preference."""
    key = (token or "").strip().lower()
    if key in {"afternoon", "evening"}:
        return 4
    return 3  # morning / noon


def _parse_day(text: str, base: datetime) -> datetime | None:
    rel = _RELATIVE_DAY.search(text)
    if rel:
        token = re.sub(r"\s+", " ", (rel.group(1) or "").strip().lower())
        if token in {"today", "tonight"}:
            return base
        if token in {
            "tomorrow",
            "tmrw",
            "tmorrow",
            "tomorow",
            "tommorrow",
            "tommorow",
        }:
            return base + timedelta(days=1)
        if token in {
            "day after tomorrow",
            "the day after tomorrow",
        }:
            return base + timedelta(days=2)
        if token in {
            "next week",
            "a week from now",
            "a week from today",
            "in a week",
        }:
            return base + timedelta(days=7)

    wd = _WEEKDAY.search(text)
    if not wd:
        return None
    day_token = (wd.group("day") or "").lower()
    target = _WEEKDAYS.get(day_token)
    if target is None:
        return None
    mod = (wd.group("mod") or "").strip().lower()
    force_next = mod.startswith("next")
    # "coming Monday" ≈ next occurrence forced ahead when today is that weekday.
    days_ahead = (target - base.weekday()) % 7
    if days_ahead == 0 and (force_next or base.hour >= 17 or mod.startswith("coming")):
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def _parse_clock(text: str) -> tuple[int, int, bool]:
    """Return (hour, minute, found). Prefers explicit am/pm / o'clock cues."""
    best: tuple[int, int] | None = None

    for match in _OCLOCK.finditer(text):
        h = int(match.group("h"))
        if not 1 <= h <= 12:
            continue
        # Bare o'clock in shop booking: 1–7 → afternoon, 8–12 → morning/noon.
        if 1 <= h <= 7:
            h += 12
        elif h == 12:
            h = 12
        best = (h, 0)

    for match in _CLOCK.finditer(text):
        # Skip 4-digit years (2024) and long digit runs (phones / VINs).
        tail = text[match.start() : match.start() + 6]
        if re.match(r"(?:19|20)\d{2}\b", tail):
            continue
        if re.match(r"\d{3,}", text[match.start() :]):
            continue
        # Skip the hour token already consumed by "N o'clock".
        after = text[match.end() : match.end() + 8].lower()
        if after.lstrip().startswith(("o'clock", "oclock")):
            continue
        h = int(match.group("h"))
        m = int(match.group("m") or 0)
        ampm = (match.group("ampm") or "").lower().replace(".", "")
        # Skip bare numbers that are likely years / phone fragments.
        if not ampm and (h > 23 or m > 59):
            continue
        if not ampm and h > 12 and h <= 23:
            # Accept 24h clock only with explicit minutes (14:30), not bare 14/20.
            if match.group("m") is None:
                continue
            best = (h, m)
            continue
        if not ampm and h > 12:
            continue
        # Require am/pm for ambiguous 1–12 unless preceded by "at" / day cue.
        prefix = text[max(0, match.start() - 12) : match.start()].lower()
        has_at = bool(re.search(r"\bat\s*$", prefix))
        has_day_cue = bool(
            re.search(
                r"\b(today|tomorrow|tonight|tmrw|next\s+week|"
                r"day\s+after\s+tomorrow)\s*$",
                prefix,
            )
            or re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"mon|tues?|weds?|thurs?|thur|fri|sat|sun)\s*$",
                prefix,
            )
        )
        if not ampm and not has_at and not has_day_cue and h <= 12:
            # Still accept "2:30" style with minutes.
            if match.group("m") is None:
                continue
        if ampm.startswith("p") and h < 12:
            h += 12
        elif ampm.startswith("a") and h == 12:
            h = 0
        elif not ampm and (has_at or has_day_cue) and 1 <= h <= 7:
            # "today at 3" / "today 3" in shop booking → afternoon.
            h += 12
        if 0 <= h <= 23 and 0 <= m <= 59:
            best = (h, m)
    if best is None:
        return 9, 0, False
    return best[0], best[1], True
