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


_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
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
    r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
_RELATIVE_DAY = re.compile(
    r"\b(today|tomorrow|tonight)\b",
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
        return PreferredDatetime(None, None, "none")

    if day is None:
        # Time-only: today if still ahead, otherwise tomorrow.
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
        return PreferredDatetime(start, end, precision)

    if has_clock:
        start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        return PreferredDatetime(start, start + timedelta(hours=1), "clock")

    if part is not None:
        h, m = _part_of_day_hours(part.group(0))
        start = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
        span = _part_of_day_span(part.group(0))
        return PreferredDatetime(start, start + timedelta(hours=span), "part_of_day")

    # Day only — window for filtering openings; do not treat 08:00 as chosen.
    start = datetime(day.year, day.month, day.day, 8, 0, tzinfo=tz)
    end = datetime(day.year, day.month, day.day, 17, 0, tzinfo=tz)
    return PreferredDatetime(start, end, "day")


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
        token = (rel.group(1) or "").lower()
        if token in {"today", "tonight"}:
            return base
        if token == "tomorrow":
            return base + timedelta(days=1)

    wd = _WEEKDAY.search(text)
    if not wd:
        return None
    target = _WEEKDAYS[wd.group(2).lower()]
    force_next = bool(wd.group(1))
    days_ahead = (target - base.weekday()) % 7
    if days_ahead == 0 and (force_next or base.hour >= 17):
        days_ahead = 7
    if force_next and days_ahead == 0:
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
            re.search(r"\b(today|tomorrow|tonight)\s*$", prefix)
            or re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*$",
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
