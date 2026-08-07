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

# Tone
- Sound warm, patient, and polite — like a helpful front-desk counselor, not a robot checklist.
- Use natural kindness: short acknowledgements such as "Sure", "Of course", "Happy to help", or "No problem" when they fit.
- Soften bad news with empathy ("I'm sorry, that time isn't open") and invite another choice.
- Stay brief and speakable. Warm does not mean long or chatty.

# Goal
Only create, change, or cancel a reservation after all three are confirmed:
1. Customer identity — for new callers without a real name on file, ask their name before booking
2. Requested service — one of the shop's real catalog services
3. Preferred date/time — a concrete day and clock time the customer chose, that is actually free and within shop business hours

# Scope
- Stay on shop and vehicle service topics only: booking, rescheduling, cancellation,
  availability, catalog service questions, maintenance, and repair status.
- If the customer says something unrelated (weather, news, jokes, personal chit-chat,
  unrelated businesses, etc.), do not follow that topic.
- Kindly acknowledge without arguing, then gently guide them back to how you can help
  with vehicle service (book, change, cancel, or a shop question). One short warm redirect.
- Do not debate, role-play at length, or offer general advice outside the shop.

# Behavior
- Never guess. Customer info, service details, and availability always come from tool/function results. If unsure, say you'll check and call the function.
- Ask only one thing at a time. Do not stack questions.
- If the customer is new (no real name yet) and ready to book, ask for their name before the final booking confirmation.
- When the customer wants to book, ask when they want to come in. Do not volunteer available times.
- Only list openings when the customer asks what times are available.
- If their requested time is taken or outside business hours, say it is not available and ask them to pick another time — do not auto-suggest alternatives unless they ask for openings.
- If only the day is closed or has no openings, keep their clock time and re-ask only for another day. If only the specific clock is taken (or outside hours) on an open day, keep the day and re-ask only for another time.
- Never tell the customer they are booked (or ask to confirm a booking) for a time that was not returned as a free opening.
- If the customer is vague ("anytime", "you know the one"), ask a short clarifying question.
- If a service name matches several catalog items, offer 2–3 candidates and let them choose.
- Right before the final create/change/cancel, get a one-sentence summary confirmation.
  Example: "March 5 at 2 PM for an oil change — shall I book that for you?"
- Never book, change, or cancel until you hear a clear yes.
- When listing openings, merge contiguous free slots into continuous from–to windows
  (e.g. bookable 8–8:30 and 8:30–9 becomes "Wednesday from 8:00 AM to 9:00 AM").
  Say only when the window starts and ends — never total duration. Never list each micro-slot separately.
- Do not say "go ahead" or "going" in replies.
- Keep replies short and conversational. No lists, markdown, or long explanations.
- Only use the customer's name if it is a real personal name. Never address them as Unknown, Guest, Going, Gonna, or similar placeholders — just skip the name.
- Never start a reply with "Going" or "Gonna" as if it were the customer's name.
- On the first reply only, open with "Hello, this is {shop_name}" (and their name if known) and warmly ask how you can help. Address them by name only in that first reply — never on later turns.
- On later turns, skip the greeting and the name; go straight to the point with a kind tone.

# Closing
When the request is done, summarize the result in one sentence and thank them.
You may offer help once ("Is there anything else I can help you with?").
If the customer declines or says they are done, give a warm farewell and end —
do not ask again what else they need.
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


def format_day(dt: datetime | None) -> str:
    """Weekday name only (e.g. Friday) for partial date acknowledgements."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=_SHOP_TZ)
    else:
        local = dt.astimezone(_SHOP_TZ)
    return local.strftime("%A")


def _clock_bit(dt: datetime) -> str:
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=_SHOP_TZ)
    else:
        local = dt.astimezone(_SHOP_TZ)
    clock = local.strftime("%I:%M %p")
    return clock[1:] if clock.startswith("0") else clock


def format_duration(start: datetime | None, end: datetime | None) -> str:
    """Spoken total length between start and end (e.g. 1 hour, 30 minutes)."""
    if start is None or end is None:
        return ""
    total_sec = int((end - start).total_seconds())
    if total_sec <= 0:
        return ""
    total_min = max(1, (total_sec + 59) // 60)  # round up partial minutes
    hours, minutes = divmod(total_min, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if minutes:
        parts.append(f"{minutes} minute" if minutes == 1 else f"{minutes} minutes")
    return " ".join(parts)


def format_when_range(start: datetime | None, end: datetime | None = None) -> str:
    """Spoken opening as from–to only (no total duration).

    Example: Wednesday from 8:00 AM to 9:00 AM.
    """
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


def _as_slot_pair(
    item: datetime | tuple[datetime, datetime | None] | None,
) -> tuple[datetime, datetime | None] | None:
    if item is None:
        return None
    if isinstance(item, tuple):
        start = item[0] if item else None
        end = item[1] if len(item) > 1 else None
    else:
        start, end = item, None
    if start is None:
        return None
    return (start, end)


def merge_contiguous_windows(
    slots: list[datetime] | list[tuple[datetime, datetime | None]],
) -> list[tuple[datetime, datetime | None]]:
    """Collapse consecutive free slots into continuous availability windows.

    08:00–08:30 + 08:30–09:00 → 08:00–09:00 (not two micro-slots).
    """
    pairs: list[tuple[datetime, datetime | None]] = []
    for item in slots:
        pair = _as_slot_pair(item)
        if pair is not None:
            pairs.append(pair)
    if not pairs:
        return []

    def _sort_key(pair: tuple[datetime, datetime | None]) -> datetime:
        start = pair[0]
        if start.tzinfo is None:
            return start.replace(tzinfo=_SHOP_TZ)
        return start

    pairs.sort(key=_sort_key)
    merged: list[tuple[datetime, datetime | None]] = []
    cur_start, cur_end = pairs[0]
    for start, end in pairs[1:]:
        if cur_end is not None and end is not None and start <= cur_end:
            if end > cur_end:
                cur_end = end
            continue
        if cur_end is not None and end is None and start <= cur_end:
            # Point-in-time falls inside the open window — drop it.
            continue
        if cur_end is None and end is not None and start == cur_start:
            cur_end = end
            continue
        merged.append((cur_start, cur_end))
        cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


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
        return f"{who}{when_bit} for {service_bit} — shall I book that for you?"
    return f"{who}I can book you for {service_bit}. Does that sound good?"


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
    return f"{who}just to confirm — cancel {detail}? Say yes and I'll take care of it."


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
        return f"{who}happy to move you{service_bit} to {when_bit} — shall I do that?"
    return f"{who}no problem — what new day and time work best for you{service_bit}?"


def summarize_done(
    *,
    action: str,
    customer_name: str | None = None,
    service_name: str | None = None,
    when: datetime | str | None = None,
    keep_open: bool = False,
) -> str:
    """Confirm a completed action.

    keep_open=True (phone): end with an offer to help more so the call stays open.
    keep_open=False (SMS): closed farewell suitable for a final message.
    """
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    when_bit = format_when(when) if isinstance(when, datetime) else (when or "")
    service_bit = f" for {service_name}" if service_name else ""
    more = " Is there anything else I can help you with?" if keep_open else ""
    if action == "book":
        if when_bit:
            core = (
                f"{who}you're all set — booked{service_bit} for {when_bit}. "
                "We'll send a reminder."
            )
        else:
            core = f"{who}you're all set — booked{service_bit}. We'll send a reminder."
        return f"{core}{more}" if keep_open else f"{core} Thanks so much — take care!"
    if action == "reschedule":
        if when_bit:
            core = f"{who}all set — I've moved you{service_bit} to {when_bit}."
        else:
            core = f"{who}all set — your appointment's been moved."
        return f"{core}{more}" if keep_open else f"{core} Looking forward to seeing you!"
    if action == "cancel":
        core = f"{who}you're all cancelled — no problem at all."
        if keep_open:
            return f"{core} Is there anything else I can help you with?"
        return f"{core} Call or text anytime if you'd like to rebook."
    core = f"{who}all done — happy to help."
    return f"{core}{more}" if keep_open else f"{core} Take care!"


_FAREWELL_CUES = re.compile(
    r"(?is)^\s*("
    r"good\s*bye|goodbye|bye(\s+bye)?|hang\s*up|"
    r"that(?:'s|\s+is)\s+all(?:\s+i\s+need)?"
    r"|that'?s\s+it(?:\s+for\s+me)?"
    r"|nothing\s+(?:else|more)(?:\s+(?:for\s+me|i\s+need))?"
    r"|no(?:pe|ah)?[,!.\s]+(?:thanks|thank\s+you(?:\s+so\s+much)?|"
    r"that(?:'s|\s+is)\s+(?:it|all)|nothing(?:\s+(?:else|more))?)"
    r"|i(?:'?m|\s+am)\s+(?:all\s+)?(?:good|done|set|fine)"
    r"|all\s+good|we(?:'?re|\s+are)\s+good|"
    r"not\s+right\s+now|"
    r"that(?:'ll|\s+will)\s+be\s+all|"
    r"have\s+a\s+(?:good|great)\s+(?:one|day|night)|"
    r"talk\s+(?:to\s+you\s+)?later"
    r")\s*[.!]?\s*$",
)

# After "Anything else?" only — bare no / short declines (comma & fillers ok).
_SOFT_NO = re.compile(
    r"(?is)^\s*("
    r"no(?:pe|ah)?"
    r"(?:[,!.\s]+(?:"
    r"thanks|thank\s+you(?:\s+so\s+much)?|"
    r"i(?:'?m|\s+am)\s+(?:all\s+)?(?:good|fine|set|done)|"
    r"that(?:'s|\s+is)\s+(?:all|it)|"
    r"nothing(?:\s+(?:else|more))?|"
    r"all\s+good|"
    r"i(?:'?m|\s+am)\s+good"
    r"))*"
    r"|nothing(?:\s+(?:else|more))?(?:\s+for\s+me)?"
    r"|none|no\s+more|"
    r"that(?:'s|\s+is)\s+(?:all|it)(?:\s+(?:for\s+me|i\s+need))?"
    r"|i(?:'?m|\s+am)\s+(?:all\s+)?(?:good|fine|set|done)|"
    r"all\s+good|not\s+right\s+now|"
    r"that(?:'ll|\s+will)\s+be\s+all|"
    r"i(?:'?m|\s+am)\s+all\s+set|"
    r"thanks(?:\s+a\s+lot)?|thank\s+you(?:\s+so\s+much)?|"
    r"ok(?:ay)?(?:[,!.\s]+(?:thanks|thank\s+you))?"
    r")\s*[.!]?\s*$",
)

_ANYTHING_ELSE = re.compile(
    r"anything\s+else|need\s+anything\s+else|help\s+with\s+anything\s+else|"
    r"is\s+there\s+anything\s+else|what\s+else\s+(?:can|do)\s+you\s+need|"
    r"need\s+anything\s+more|anything\s+else\s+i\s+can\s+help",
    re.I,
)


def looks_like_farewell(text: str | None) -> bool:
    """True when the caller is wrapping up / done with the call."""
    if not text or not text.strip():
        return False
    return bool(_FAREWELL_CUES.search(text.strip()))


def is_anything_else_question(text: str | None) -> bool:
    return bool(text and _ANYTHING_ELSE.search(text))


def looks_like_soft_no(text: str | None) -> bool:
    """Short decline after an open 'anything else?' offer."""
    if not text or not text.strip():
        return False
    return bool(_SOFT_NO.search(text.strip()))


def wants_to_end_after_offer(
    customer_text: str | None,
    *,
    pending_question: str | None = None,
    last_assistant_text: str | None = None,
) -> bool:
    """True when caller declines/wraps up after an 'anything else?' offer."""
    offered = is_anything_else_question(pending_question) or is_anything_else_question(
        last_assistant_text
    )
    if not offered:
        return looks_like_farewell(customer_text)
    return looks_like_farewell(customer_text) or looks_like_soft_no(customer_text)

def ask_service(*, customer_name: str | None = None) -> str:
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    return f"{who}sure — what service can I help you with?"


def ask_replacement_service(
    *,
    customer_name: str | None = None,
    current_service: str | None = None,
) -> str:
    """Ask which service to switch an existing booking to."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    if current_service:
        return f"{who}sure — what would you like instead of {current_service}?"
    return f"{who}sure — what service should we switch you to?"


def ask_name(*, customer_name: str | None = None) -> str:
    """Ask for the caller's name before booking a new / unnamed customer."""
    _ = customer_name  # never address placeholders; keep signature consistent
    return "may I have your name so I can put the booking under you?"


_NAME_QUESTION = re.compile(
    r"what'?s your name|your name so i can|may i (have|get) your name|"
    r"can i (have|get) your name|who am i booking",
    re.I,
)


def is_name_question(text: str | None) -> bool:
    """True when the pending/follow-up question is asking for the customer's name."""
    return bool(text and _NAME_QUESTION.search(text))


def ask_time(
    *,
    customer_name: str | None = None,
    service_name: str | None = None,
    known_day: datetime | str | None = None,
) -> str:
    """Ask for a concrete clock time. If a day is already known, only ask for time."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    service_bit = f" for {service_name}" if service_name else ""
    day_bit = (
        format_day(known_day)
        if isinstance(known_day, datetime)
        else (known_day or "")
    ).strip()
    if day_bit:
        return f"{who}got it — {day_bit}{service_bit}. What time works best?"
    return f"{who}what day and time work best for you{service_bit}?"


def ask_date(
    *,
    customer_name: str | None = None,
    service_name: str | None = None,
    known_time: datetime | str | None = None,
) -> str:
    """Ask for the appointment day. If a clock time is already known, only ask for day."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    service_bit = f" for {service_name}" if service_name else ""
    if isinstance(known_time, datetime):
        time_bit = _clock_bit(known_time)
    else:
        time_bit = (known_time or "").strip()
    if time_bit:
        return f"{who}got it — {time_bit}{service_bit}. What day works best?"
    return f"{who}what day works best for you{service_bit}?"


def time_unavailable(
    when: datetime | str | None = None,
    *,
    customer_name: str | None = None,
    ask: str | None = None,
    day_only: bool = False,
) -> str:
    """Requested slot unavailable — re-ask only the broken half when known.

    ``ask``: ``date`` (re-ask day, keep clock), ``time`` (re-ask clock, keep day),
    or ``both`` / None (either day or time).
    ``day_only``: customer only named a day (e.g. closed Sunday) — omit invented clock.
    """
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    aspect = (ask or "both").strip().lower()
    if aspect not in {"date", "time", "both"}:
        aspect = "both"

    when_dt = when if isinstance(when, datetime) else None
    when_bit = format_when(when_dt) if when_dt is not None else (when or "")
    day_bit = format_day(when_dt) if when_dt is not None else ""
    clock_bit = _clock_bit(when_dt) if when_dt is not None else ""

    if aspect == "date":
        if day_bit and day_only:
            return (
                f"{who}I'm sorry, {day_bit} isn't available. "
                "What other day works for you?"
            )
        if day_bit and clock_bit and not day_only:
            return (
                f"{who}I'm sorry, {day_bit} isn't available at {clock_bit}. "
                "What other day works for you?"
            )
        if day_bit:
            return (
                f"{who}I'm sorry, {day_bit} isn't available. "
                "What other day works for you?"
            )
        return (
            f"{who}I'm sorry, that day isn't available. "
            "What other day works for you?"
        )

    if aspect == "time":
        if day_bit and clock_bit:
            return (
                f"{who}I'm sorry, {clock_bit} on {day_bit} isn't available. "
                "What other time works that day?"
            )
        if clock_bit:
            return (
                f"{who}I'm sorry, {clock_bit} isn't available. "
                "What other time works for you?"
            )
        return (
            f"{who}I'm sorry, that time isn't available. "
            "What other time works for you?"
        )

    if when_bit and not day_only:
        return (
            f"{who}I'm sorry, {when_bit} isn't available. "
            "What other day or time works for you?"
        )
    if day_bit:
        return (
            f"{who}I'm sorry, {day_bit} isn't available. "
            "What other day works for you?"
        )
    return (
        f"{who}I'm sorry, that time isn't available. "
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
        return f"{who}just to make sure — did you mean {names[0]}?"
    if len(names) == 2:
        return f"{who}just to make sure — did you mean {names[0]}, or {names[1]}?"
    return (
        f"{who}just to make sure — did you mean {names[0]}, {names[1]}, or {names[2]}?"
    )


def offer_slots_spoken(
    slots: list[datetime] | list[tuple[datetime, datetime | None]],
    *,
    customer_name: str | None = None,
    service_name: str | None = None,
    limit: int = 3,
) -> str:
    """List openings as merged continuous from–to windows.

    Contiguous bookable micro-slots (e.g. 8–8:30, 8:30–9) are spoken as one
    block (8–9). Accepts starts or (start, end) pairs.
    """
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    service_bit = f" for {service_name}" if service_name else ""
    options: list[str] = []
    for start, end in merge_contiguous_windows(slots)[:limit]:
        spoken = format_when_range(start, end)
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
    got = (
        f"I've got a few openings{service_bit}"
        if service_bit
        else "I've got a few openings"
    )
    return (
        f"{who}{got}: {spoken}. "
        "Would you like the first one, or a different time?"
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
    return f"{who}how can I help you today?"


def redirect_to_service_topic(*, customer_name: str | None = None) -> str:
    """Kindly steer off-topic callers back to shop/vehicle service help."""
    name = spoken_first_name(customer_name)
    who = f"{name}, " if name else ""
    return (
        f"{who}I appreciate that — I'm mainly here to help with vehicle service "
        "at the shop, like booking, changing, or canceling a visit, or a repair question. "
        "What can I help you with for your vehicle today?"
    )


# Clear non-service chat — weather, entertainment, general knowledge, etc.
_OFF_TOPIC = re.compile(
    r"(?is)\b("
    r"weather|forecast|temperature|"
    r"joke|jokes|funny|riddle|"
    r"sports?|score|game last night|"
    r"stock\s*market|cryptocurrency|bitcoin|"
    r"politics|election|president|"
    r"news\s+today|latest\s+news|"
    r"movie|film|song|music|recipe|cooking|"
    r"tell me (a |something )?(joke|story|fun fact)|"
    r"who (won|is the)|what'?s (your favorite|the capital)|"
    r"how (old are you|are you doing today)|"
    r"are you (a )?(real|human|robot|ai)|"
    r"sing (me )?(a )?song|"
    r"play a game"
    r")\b",
)

# Shop / vehicle service signals — used to avoid false off-topic redirects.
_SERVICE_SIGNAL = re.compile(
    r"(?is)\b("
    r"book|schedule|appointment|appt|reservation|booking|"
    r"cancel|reschedule|available|opening|slot|"
    r"oil|brake|tire|tires|battery|inspection|align|"
    r"repair|service|maintenance|mechanic|shop|"
    r"car|vehicle|truck|van|suv|vin|"
    r"price|cost|quote|estimate|"
    r"come in|drop off|pick up"
    r")\b",
)


def looks_like_off_topic(text: str | None) -> bool:
    """True when the customer is not talking about shop/vehicle service."""
    if not text or not text.strip():
        return False
    raw = text.strip()
    if looks_like_booking_desire(raw) or looks_like_reschedule_or_cancel_desire(raw):
        return False
    if _SERVICE_SIGNAL.search(raw):
        return False
    if _OFF_TOPIC.search(raw):
        return True
    # Greeting / pure chit-chat without any service wording.
    if re.fullmatch(
        r"(?is)\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|how are you"
        r"( doing)?|what'?s up|yo|thanks|thank you)[.!?]?\s*",
        raw,
    ):
        return False  # greeting — purpose ask is fine elsewhere
    # Unrelated when no service signal and looks like general Q&A / banter.
    if re.search(
        r"(?is)^\s*(what|who|when|where|why|how|tell|can you|do you know)\b",
        raw,
    ):
        return True
    return False


_PURPOSE_QUESTION = re.compile(
    r"what can i help|how can i help you today|what (do|can) you need|"
    r"what can we help|how can i help",
    re.I,
)
_BOOKING_DESIRE_TEXT = re.compile(
    r"\b(book|schedule|appointment|appt|booking|visit)\b|"
    r"\breserv\w*\b",
    re.I,
)
# Time-change mentions "appointment" but must not look like a new booking.
# Exclude "oil change …" so maintenance booking is not treated as a reschedule.
from app.agents.intent.reschedule_text import RESCHEDULE_PATTERN as _RESCHEDULE_DESIRE
_CANCEL_DESIRE = re.compile(
    r"\b(cancel|cancellation|call off)\b",
    re.I,
)


def is_purpose_question(text: str | None) -> bool:
    """True when the pending/follow-up question is the open-ended purpose ask."""
    return bool(text and _PURPOSE_QUESTION.search(text))


def looks_like_booking_desire(text: str | None) -> bool:
    """True when customer text shows they want to book (service may still be unknown)."""
    if not text:
        return False
    if looks_like_reschedule_or_cancel_desire(text):
        return False
    return bool(_BOOKING_DESIRE_TEXT.search(text))


def looks_like_reschedule_desire(text: str | None) -> bool:
    """True when customer asks to move/change an existing appointment time."""
    return bool(text and _RESCHEDULE_DESIRE.search(text))


def looks_like_reschedule_or_cancel_desire(text: str | None) -> bool:
    """True when customer asks to change or cancel an existing appointment."""
    return bool(
        text
        and (
            _RESCHEDULE_DESIRE.search(text) or _CANCEL_DESIRE.search(text)
        )
    )


def greeting(*, shop_name: str | None = None, customer_name: str | None = None) -> str:
    """First-turn opening: introduce the shop, then ask what they need."""
    intro = first_reply_prefix(
        shop_name=shop_name, customer_name=customer_name
    ).rstrip()
    return f"{intro} {ask_purpose()}"
