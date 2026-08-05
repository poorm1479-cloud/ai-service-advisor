"""Shared booking-counselor persona and short spoken copy helpers.

Used by voice/SMS reply generators (and as an LLM system prompt when swapped in).
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

# Keep spoken times aligned with Schedule / availability engines.
_SHOP_TZ = ZoneInfo("America/Los_Angeles")

COUNSELOR_SYSTEM_PROMPT = """You are the booking AI counselor for {shop_name}.
You talk with customers by phone or SMS and handle service booking, changes, and cancellations.

# Goal
Only create, change, or cancel a reservation after all three are confirmed:
1. Customer identity — for new callers without a real name on file, ask their name before booking
2. Requested service — one of the shop's real catalog services
3. Preferred date/time — a concrete day and clock time the customer chose, that is actually free and within shop business hours

# Behavior
- Never guess. Customer info, service details, and availability always come from tool/function results. If unsure, say you'll check and call the function.
- Ask only one thing at a time. Do not stack questions.
- If the customer is new (no real name yet) and ready to book, ask for their name before the final booking confirmation.
- When the customer wants to book, ask when they want to come in. Do not volunteer available times.
- Only list openings when the customer asks what times are available.
- If their requested time is taken or outside business hours, say it is not available and ask them to pick another time — do not auto-suggest alternatives unless they ask for openings.
- Never tell the customer they are booked (or ask to confirm a booking) for a time that was not returned as a free opening.
- If the customer is vague ("anytime", "you know the one"), ask a short clarifying question.
- If a service name matches several catalog items, offer 2–3 candidates and let them choose.
- Right before the final create/change/cancel, get a one-sentence summary confirmation.
  Example: "Alex, March 5 at 2 PM for an oil change — should I book that?"
- Never book, change, or cancel until you hear a clear yes.
- When listing openings, always say each as a from–to window (start to end), not a single start time.
- Do not say "go ahead" or "going" in replies.
- Keep replies short and conversational. No lists, markdown, or long explanations.
- Only use the customer's name if it is a real personal name. Never address them as Unknown, Guest, Going, Gonna, or similar placeholders — just skip the name.
- Never start a reply with "Going" or "Gonna" as if it were the customer's name.
- On the first reply only, open with "Hello, this is {shop_name}" and ask what they need. On later turns, skip the greeting and go straight to the point.

# Closing
When the request is done, summarize the result in one sentence and wrap up the conversation.
"""


def build_system_prompt(*, shop_name: str | None = None) -> str:
    name = (shop_name or "").strip() or "the shop"
    return COUNSELOR_SYSTEM_PROMPT.format(shop_name=name)


# Placeholder / non-personal tokens — never speak these as a customer name.
_PLACEHOLDER_NAMES = frozenset(
    {
        "unknown",
        "unknown customer",
        "n/a",
        "na",
        "none",
        "null",
        "going",
        "gonna",
    }
)


def is_placeholder_name(customer_name: str | None) -> bool:
    """True when CRM name is missing or a non-personal placeholder."""
    raw = (customer_name or "").strip()
    if not raw:
        return True
    if raw.casefold() in _PLACEHOLDER_NAMES:
        return True
    first = raw.split()[0].strip()
    return not first or first.casefold() in _PLACEHOLDER_NAMES


def spoken_first_name(customer_name: str | None) -> str:
    """First name for spoken/SMS copy; empty if missing or a CRM placeholder."""
    if is_placeholder_name(customer_name):
        return ""
    return (customer_name or "").strip().split()[0].strip()


def needs_customer_name(customer_name: str | None) -> bool:
    """True when we must ask for a name before creating a booking."""
    return not bool(spoken_first_name(customer_name))


_BANNED_ADDRESS_PREFIX = re.compile(
    r"^\s*(?:going|gonna|unknown(?:\s+customer)?)\s*,?\s+",
    re.I,
)
_HELLO_BANNED_NAME = re.compile(
    r"(?i)^(hello)\s+(?:going|gonna|unknown(?:\s+customer)?)\b,?\s*",
)


def sanitize_spoken_reply(text: str | None) -> str:
    """Strip mistaken non-name address tokens (e.g. 'Going, …' / 'Hello Going')."""
    out = (text or "").strip()
    if not out:
        return ""
    out = _HELLO_BANNED_NAME.sub(r"\1, ", out, count=1)
    while True:
        cleaned = _BANNED_ADDRESS_PREFIX.sub("", out, count=1)
        if cleaned == out:
            break
        out = cleaned.lstrip()
    return out.strip()


def format_when(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=_SHOP_TZ)
    else:
        local = dt.astimezone(_SHOP_TZ)
    return local.strftime("%A at %I:%M %p").replace(" 0", " ")


def _clock_bit(dt: datetime) -> str:
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=_SHOP_TZ)
    else:
        local = dt.astimezone(_SHOP_TZ)
    clock = local.strftime("%I:%M %p")
    return clock[1:] if clock.startswith("0") else clock


def format_when_range(start: datetime | None, end: datetime | None = None) -> str:
    """Spoken opening as a from–to window (e.g. Wednesday from 8:00 AM to 9:00 AM)."""
    if start is None:
        return ""
    if end is None:
        return format_when(start)
    if start.tzinfo is None:
        start_local = start.replace(tzinfo=_SHOP_TZ)
    else:
        start_local = start.astimezone(_SHOP_TZ)
    if end.tzinfo is None:
        end_local = end.replace(tzinfo=_SHOP_TZ)
    else:
        end_local = end.astimezone(_SHOP_TZ)
    day = start_local.strftime("%A")
    start_clock = _clock_bit(start_local)
    end_clock = _clock_bit(end_local)
    if start_local.date() != end_local.date():
        end_day = end_local.strftime("%A")
        return f"{day} from {start_clock} to {end_day} {end_clock}"
    return f"{day} from {start_clock} to {end_clock}"


def summarize_booking_confirm(
    *,
    customer_name: str | None,
    service_name: str | None,
    when: datetime | str | None,
) -> str:
    name = spoken_first_name(customer_name)
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    service_bit = service_name or "that service"
    who = f"{name}, " if name else ""
    if when_bit:
        return f"{who}{when_bit} for {service_bit} — should I book that?"
    return f"{who}book you for {service_bit}? Just say yes if that works."


def summarize_cancel_confirm(
    *,
    customer_name: str | None,
    service_name: str | None,
    when: datetime | str | None = None,
) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    if service_name and when_bit:
        detail = f"{service_name} on {when_bit}"
    elif service_name:
        detail = service_name
    elif when_bit:
        detail = when_bit
    else:
        detail = "that appointment"
    return f"{who}cancel {detail}? Just say yes and I'll take care of it."


def summarize_reschedule_confirm(
    *,
    customer_name: str | None,
    service_name: str | None,
    when: datetime | str | None,
) -> str:
    name = spoken_first_name(customer_name)
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    service_bit = f" for {service_name}" if service_name else ""
    who = f"{name}, " if name else ""
    if when_bit:
        return f"{who}move you{service_bit} to {when_bit} — want me to do that?"
    return f"{who}ready to move that appointment{service_bit}. What day works?"


def summarize_done(
    *,
    action: str,
    customer_name: str | None = None,
    service_name: str | None = None,
    when: datetime | str | None = None,
) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    service_bit = f" for {service_name}" if service_name else ""
    if action == "book":
        if when_bit:
            return f"{who}you're booked{service_bit} for {when_bit}. We'll send a reminder. Take care!"
        return f"{who}you're booked{service_bit}. We'll send a reminder. Take care!"
    if action == "reschedule":
        if when_bit:
            return f"{who}all set — moved you{service_bit} to {when_bit}. See you then!"
        return f"{who}all set — your appointment's been moved. See you then!"
    if action == "cancel":
        return f"{who}you're all cancelled. Call or text anytime if you want to rebook."
    return f"{who}all done. Take care!"


def ask_service(*, customer_name: str | None = None) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    return f"{who}what service do you need?"


def ask_name(*, customer_name: str | None = None) -> str:
    """Ask for the caller's name before booking a new / unnamed customer."""
    _ = customer_name  # never address placeholders; keep signature consistent
    return "what's your name so I can put the booking under you?"


_NAME_QUESTION = re.compile(
    r"what'?s your name|your name so i can|may i (have|get) your name|"
    r"can i (have|get) your name|who am i booking",
    re.I,
)


def is_name_question(text: str | None) -> bool:
    """True when the pending/follow-up question is asking for the customer's name."""
    return bool(text and _NAME_QUESTION.search(text))


def ask_time(*, customer_name: str | None = None, service_name: str | None = None) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    service_bit = f" for {service_name}" if service_name else ""
    return f"{who}what day and time work best{service_bit}?"


def time_unavailable(
    when: datetime | str | None = None,
    *,
    customer_name: str | None = None,
) -> str:
    """Requested clock time is taken or outside hours — ask for another; no openings."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    if when_bit:
        return (
            f"{who}{when_bit} isn't available. "
            "What other day or time works for you?"
        )
    return (
        f"{who}that time isn't available. "
        "What other day or time works for you?"
    )


def offer_service_candidates(
    candidates: list[str], *, customer_name: str | None = None
) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    names = [c for c in candidates if c][:3]
    if not names:
        return ask_service(customer_name=customer_name)
    if len(names) == 1:
        return f"{who}did you mean {names[0]}?"
    if len(names) == 2:
        return f"{who}did you mean {names[0]}, or {names[1]}?"
    return f"{who}did you mean {names[0]}, {names[1]}, or {names[2]}?"


def offer_slots_spoken(
    slots: list[datetime] | list[tuple[datetime, datetime | None]],
    *,
    customer_name: str | None = None,
    service_name: str | None = None,
    limit: int = 3,
) -> str:
    """List openings as from–to windows. Accepts starts or (start, end) pairs."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    service_bit = f" for {service_name}" if service_name else ""
    options: list[str] = []
    for item in slots[:limit]:
        if item is None:
            continue
        if isinstance(item, tuple):
            start, end = item[0], item[1] if len(item) > 1 else None
            spoken = format_when_range(start, end)
        else:
            spoken = format_when(item)
        if spoken:
            options.append(spoken)
    if not options:
        return ask_time(customer_name=customer_name, service_name=service_name)
    if len(options) == 1:
        spoken = options[0]
    elif len(options) == 2:
        spoken = f"{options[0]}, or {options[1]}"
    else:
        spoken = ", ".join(options[:-1]) + f", or {options[-1]}"
    return (
        f"{who}I've got{service_bit}: {spoken}. "
        "Want the first one, or a different time?"
    )


def first_reply_prefix(
    *, shop_name: str | None = None, customer_name: str | None = None
) -> str:
    """Shop intro used only on the first AI turn (SMS / spoken prefix)."""
    name = spoken_first_name(customer_name)
    shop = (shop_name or "").strip()
    if shop and name:
        return f"Hello {name}, this is {shop}. "
    if shop:
        return f"Hello, this is {shop}. "
    if name:
        return f"Hello {name}. "
    return "Hello. "


def ask_purpose(*, customer_name: str | None = None) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    return f"{who}what can I help you with?"


_PURPOSE_QUESTION = re.compile(
    r"what can i help|what (do|can) you need|what can we help|how can i help",
    re.I,
)
_BOOKING_DESIRE_TEXT = re.compile(
    r"\b(book|schedule|appointment|appt|booking|visit)\b|"
    r"\breserv\w*\b",
    re.I,
)


def is_purpose_question(text: str | None) -> bool:
    """True when the pending/follow-up question is the open-ended purpose ask."""
    return bool(text and _PURPOSE_QUESTION.search(text))


def looks_like_booking_desire(text: str | None) -> bool:
    """True when customer text shows they want to book (service may still be unknown)."""
    return bool(text and _BOOKING_DESIRE_TEXT.search(text))


def greeting(*, shop_name: str | None = None, customer_name: str | None = None) -> str:
    """First-turn opening: introduce the shop, then ask what they need."""
    intro = first_reply_prefix(
        shop_name=shop_name, customer_name=customer_name
    ).rstrip()
    return f"{intro} {ask_purpose()}"
