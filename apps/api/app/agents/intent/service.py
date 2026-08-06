"""Intent Agent service — heuristic intent detection grounded in shop services.

Loads the shop Service Catalog so entity extraction and booking intent
use real service names (not only hardcoded phrases). LLM-swappable via port.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.errors import AgentValidationError
from app.agents.communication.models import NormalizedMessage
from app.agents.intent.datetime_parse import parse_preferred_datetime
from app.agents.intent.models import CustomerIntent, IntentResult
from app.agents.scheduling.catalog_match import (
    CatalogServiceMatch,
    find_catalog_service_candidates,
    match_catalog_service,
)
from app.agents.scheduling.catalog_port import ServiceCatalogPort

# Affirmative reply after summary confirmation / offered slot
_AFFIRM_BOOK = re.compile(
    r"^\s*(yes|yeah|yep|yup|ok|okay|sure|confirm|book it|that works|"
    r"(the\s+)?first\s+one(\s+please)?)\s*[.!?]?\s*$",
    re.I,
)

# "Book the first available / earliest opening today" — pick earliest free slot.
# Do not match "first time customer" (new visitor).
_EARLIEST_PREF = re.compile(
    r"\b("
    r"first\s+available(\s+time)?|"
    r"first\s+(opening|slot|one|appointment)|"
    r"first\s+time\s+(today|tomorrow|this\s+(morning|afternoon|week)|in\s+the\s+(morning|afternoon))|"
    r"(today'?s?|tomorrow'?s?)\s+first(\s+(available\s+)?(time|opening|slot|one))?|"
    r"first\s+(one\s+)?(in\s+the\s+)?(morning|afternoon)|"
    r"(morning|afternoon)\s+first(\s+(available\s+)?(time|opening|slot|one))?|"
    r"earliest\s+(available\s+)?(opening|slot|time)|"
    r"next\s+available|"
    r"soonest|"
    r"as\s+soon\s+as\s+(possible|you\s+can)|"
    r"asap"
    r")\b",
    re.I,
)

# Last opening of the day / window — last available, last time, …
_LATEST_PREF = re.compile(
    r"\b("
    r"last\s+available(\s+time)?|"
    r"last\s+(opening|slot|one|appointment|time)|"
    r"latest\s+(available\s+)?(opening|slot|time)|"
    r"(today'?s?|tomorrow'?s?)\s+last(\s+(available\s+)?(time|opening|slot|one))?|"
    r"last\s+(one\s+)?(in\s+the\s+)?(morning|afternoon)|"
    r"(morning|afternoon)\s+last(\s+(available\s+)?(time|opening|slot|one))?|"
    r"end\s+of\s+(the\s+)?day"
    r")\b",
    re.I,
)

# Explicit cancel confirmation ("confirm cancel" / "yes cancel it")
_AFFIRM_CANCEL = re.compile(
    r"\b(confirm\s+cancel|yes[,.]?\s*(cancel|do\s+it)|cancel\s+it|"
    r"go\s+ahead\s+and\s+cancel)\b",
    re.I,
)

# Vague time — counselor should clarify instead of guessing a slot
_VAGUE_TIME = re.compile(
    r"\b(anytime|any\s*time|whenever|doesn'?t\s+matter|dont\s+care|"
    r"flexible)\b",
    re.I,
)

# Explicit name introductions ("my name is Alex", "I'm Sam Rivera").
# Do not treat "I'm going / I'm gonna …" as a name intro.
_NAME_EXPLICIT = re.compile(
    r"(?:my\s+name\s+is|call\s+me|"
    r"i(?:\s+am|'m)(?!\s+(?:going|gonna)\b))\s+"
    r"([A-Za-z][A-Za-z'’\-]{1,30}(?:\s+[A-Za-z][A-Za-z'’\-]{1,30}){0,2})",
    re.I,
)
_BARE_NAME = re.compile(
    r"^\s*([A-Za-z][A-Za-z'’\-]{1,30}(?:\s+[A-Za-z][A-Za-z'’\-]{1,30}){0,2})\s*[.!?]?\s*$"
)
_NAME_STOPWORDS = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "ok",
        "okay",
        "sure",
        "no",
        "nope",
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank",
        "please",
        "book",
        "booking",
        "appointment",
        "cancel",
        "reschedule",
        "morning",
        "afternoon",
        "evening",
        "today",
        "tomorrow",
        "friday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "saturday",
        "sunday",
        "available",
        "free",
        "ready",
        "here",
        "interested",
        "looking",
        "coming",
        "calling",
        "texting",
        "going",
        "gonna",
        "good",
        "fine",
        "great",
    }
)

# Asking about openings — must not auto-book or fall through to generic replies.
# Earliest/first-available booking phrases are handled separately (_EARLIEST_PREF).
_AVAILABILITY_ASK = re.compile(
    r"\b("
    r"available(\s+times?|\s+slots?|\s+openings?)?|"
    r"what times?(?:\s+(?:are|do you have|can i|for))?|"
    r"when can i (come in|bring|stop by|get in)|"
    r"any (openings?|availability|slots?|times?)|"
    r"openings?|"
    r"do you have (any )?(times?|openings?|availability|slots?)|"
    r"what'?s available|"
    r"free slots?|"
    r"times? (available|open)"
    r")\b",
    re.I,
)

# Ordered by priority — first strong match wins as primary.
_PATTERNS: list[tuple[CustomerIntent, re.Pattern[str], float]] = [
    (
        CustomerIntent.EMERGENCY,
        re.compile(
            r"\b(emergency|tow|stranded|can't drive|cannot drive|smoke|fire|accident)\b",
            re.I,
        ),
        0.95,
    ),
    (
        CustomerIntent.COMPLAINT,
        re.compile(r"\b(complaint|unhappy|upset|angry|refund|terrible|worst|manager)\b", re.I),
        0.9,
    ),
    (
        CustomerIntent.CANCEL_APPOINTMENT,
        re.compile(r"\b(cancel|cancellation|call off)\b.*\b(appointment|appt|booking)?\b", re.I),
        0.88,
    ),
    (
        CustomerIntent.RESCHEDULE,
        # Exclude "oil change …" so maintenance/booking phrases stay intact.
        # Also catch noun-style "appointment/reservation time change".
        re.compile(
            r"\b("
            r"reschedule|"
            r"move (my )?(appointment|appt|booking|reservation)|"
            r"(?<!\boil )change (my |the )?(appointment|appt|booking|reservation)(\s+time)?|"
            r"(?<!\boil )change (my |the )?(time|day)"
            r"(\s+of\s+(my\s+)?(appointment|appt|booking|reservation))?|"
            r"(appointment|appt|booking|reservation)(\s+time)?\s+change|"
            r"time\s+change|"
            r"different (day|time)|"
            r"(switch|push back|push forward) (my )?(appointment|appt|booking|reservation)"
            r")\b",
            re.I,
        ),
        0.90,
    ),
    (
        CustomerIntent.CHECK_AVAILABILITY,
        _AVAILABILITY_ASK,
        0.89,
    ),
    (
        CustomerIntent.BOOK_APPOINTMENT,
        re.compile(
            # Explicit book/schedule + appointment/reservation (service may be unknown yet).
            r"\b(book|schedule|make|set up|need)\b.*\b(appointment|appt|visit|come in|reservation|booking)\b|"
            r"\b(appointment|appt|reservation|booking)\b.*\b(book|schedule|need|make)\b|"
            # Desire to book without naming a service yet → ask which service next.
            r"\b(want|like|need|looking)\b.{0,24}\b(to\s+)?(book|schedule|reserve)\b|"
            r"\b(can i|could i|i'?d like to)\b.{0,24}\b(book|schedule|reserve)\b|"
            r"\b(here|calling|came)\b.{0,16}\b(to\s+)?(book|schedule|reserve)\b|"
            # "Book the first available / earliest opening today"
            r"\b(book|schedule|reserve)\b.{0,48}\b("
            r"first\s+available(\s+time)?|"
            r"first\s+(opening|slot|one)|"
            r"first\s+time\s+(today|tomorrow)|"
            r"earliest\s+(available\s+)?(opening|slot|time)|"
            r"next\s+available|asap"
            r")\b|"
            r"\b("
            r"first\s+available(\s+time)?|"
            r"first\s+(opening|slot)|"
            r"first\s+time\s+(today|tomorrow)|"
            r"earliest\s+(available\s+)?(opening|slot|time)|"
            r"next\s+available"
            r")\b.{0,32}\b(book|schedule|reserve|appointment|appt)\b|"
            r"^\s*(yes|yeah|yep|yup|ok|okay|sure|confirm|book it|that works|"
            r"(the\s+)?first\s+one(\s+please)?)\s*[.!?]?\s*$",
            re.I,
        ),
        0.86,
    ),
    (
        CustomerIntent.ASK_REPAIR_STATUS,
        re.compile(r"\b(status|update|ready|done|finished|progress)\b.*\b(car|vehicle|repair|ro)?\b", re.I),
        0.82,
    ),
    (
        CustomerIntent.PRICE_QUESTION,
        re.compile(r"\b(how much|price|cost|quote|estimate|\$)\b", re.I),
        0.84,
    ),
    (
        CustomerIntent.MAINTENANCE_QUESTION,
        re.compile(
            r"\b(oil change|tire|brake|maintenance|tune[- ]?up|inspection|filter|fluid)\b",
            re.I,
        ),
        0.8,
    ),
    (
        CustomerIntent.NEW_CUSTOMER,
        # Avoid "first time today" / first-available booking phrases.
        re.compile(
            r"\b("
            r"first[- ]time\s+(customer|here|visitor|caller)|"
            r"new customer|never been|new to (your )?shop|"
            r"i'?m new(\s+here)?"
            r")\b",
            re.I,
        ),
        0.78,
    ),
    (
        CustomerIntent.RETURNING_CUSTOMER,
        re.compile(r"\b(again|back|returning|usual|my regular)\b", re.I),
        0.7,
    ),
]

# Desire to receive a catalog service → treat as booking (unless advisory/price).
_BOOKING_DESIRE = re.compile(
    r"\b("
    r"need|want|looking for|get|book|schedule|make|set up|come in|reserve|"
    r"can i (get|book)|do you (do|offer)|sign me up|i'?d like"
    r")\b",
    re.I,
)
_ADVISORY = re.compile(
    r"\b(when should|how often|recommend|due for|is it time|how many miles)\b",
    re.I,
)

# Intents that must not be overridden by catalog-based booking inference.
_LOCKED_INTENTS = frozenset(
    {
        CustomerIntent.EMERGENCY,
        CustomerIntent.COMPLAINT,
        CustomerIntent.CANCEL_APPOINTMENT,
        CustomerIntent.RESCHEDULE,
        CustomerIntent.CHECK_AVAILABILITY,
        CustomerIntent.ASK_REPAIR_STATUS,
        CustomerIntent.PRICE_QUESTION,
    }
)


class IntentAgent(Agent[NormalizedMessage, IntentResult]):
    name = "intent"

    def __init__(self, catalog: ServiceCatalogPort | None = None) -> None:
        super().__init__()
        self._catalog = catalog

    async def handle(
        self, payload: NormalizedMessage, context: AgentContext
    ) -> AgentResult[IntentResult]:
        return await self.detect(payload, context)

    async def detect(
        self, message: NormalizedMessage, context: AgentContext
    ) -> AgentResult[IntentResult]:
        if not message.body.strip():
            raise AgentValidationError(
                "Cannot detect intent from empty message",
                agent=self.name,
                correlation_id=context.correlation_id,
            )

        text = message.body
        catalog_match, service_price, service_candidates = await self._match_catalog_service(
            text, context
        )

        matches: list[tuple[CustomerIntent, float]] = []
        for intent, pattern, confidence in _PATTERNS:
            if pattern.search(text):
                matches.append((intent, confidence))

        # Shop-specific service names (e.g. "Euro Oil Service") may not hit
        # hardcoded maintenance phrases — still signal service interest.
        if catalog_match is not None and not any(
            m[0] == CustomerIntent.MAINTENANCE_QUESTION for m in matches
        ):
            matches.append((CustomerIntent.MAINTENANCE_QUESTION, 0.72))

        if not matches:
            entities = _extract_entities(
                text,
                catalog_match,
                service_price,
                service_candidates=service_candidates,
                context=context,
            )
            primary, confidence, secondary = _refine_with_time_preference(
                CustomerIntent.OTHER, 0.4, [], entities, context
            )
            primary, confidence, secondary = _refine_earliest_booking(
                primary, confidence, secondary, text, entities
            )
            primary, confidence, secondary = _refine_cancel_confirmation(
                primary, confidence, secondary, text, context
            )
            primary, confidence, secondary = _refine_with_name_answer(
                primary, confidence, secondary, entities, context
            )
            result = IntentResult(
                intent=primary,
                confidence=confidence,
                entities=entities,
                secondary_intents=secondary,
                raw_excerpt=text[:240],
            )
            return AgentResult.ok(result)

        matches.sort(key=lambda m: m[1], reverse=True)
        primary, confidence = matches[0]
        secondary = [m[0] for m in matches[1:4] if m[0] != primary]

        primary, confidence, secondary = _refine_with_catalog(
            primary, confidence, secondary, text, catalog_match
        )
        # Reschedule/cancel must not attach a weak catalog hit from words like
        # "change" in "Oil Change". Keep only strong name matches.
        match_for_entities = catalog_match
        if (
            primary
            in {
                CustomerIntent.RESCHEDULE,
                CustomerIntent.CANCEL_APPOINTMENT,
            }
            and catalog_match is not None
            and catalog_match.confidence < 0.9
        ):
            match_for_entities = None
        entities = _extract_entities(
            text,
            match_for_entities,
            service_price,
            service_candidates=service_candidates,
            context=context,
        )
        primary, confidence, secondary = _refine_with_time_preference(
            primary, confidence, secondary, entities, context
        )
        primary, confidence, secondary = _refine_earliest_booking(
            primary, confidence, secondary, text, entities
        )
        primary, confidence, secondary = _refine_cancel_confirmation(
            primary, confidence, secondary, text, context
        )
        primary, confidence, secondary = _refine_with_name_answer(
            primary, confidence, secondary, entities, context
        )

        result = IntentResult(
            intent=primary,
            confidence=confidence,
            entities=entities,
            secondary_intents=secondary,
            is_emergency=primary == CustomerIntent.EMERGENCY
            or CustomerIntent.EMERGENCY in secondary,
            is_complaint=primary == CustomerIntent.COMPLAINT
            or CustomerIntent.COMPLAINT in secondary,
            raw_excerpt=text[:240],
        )
        return AgentResult.ok(result)

    async def _match_catalog_service(
        self, text: str, context: AgentContext
    ) -> tuple[CatalogServiceMatch | None, str | None, list[CatalogServiceMatch]]:
        if self._catalog is None:
            return None, None, []
        try:
            services = await self._catalog.list_bookable_services(context.shop_id)
        except Exception:  # pragma: no cover — catalog failures must not block intent
            return None, None, []
        if not services:
            return None, None, []
        candidates = find_catalog_service_candidates(text, services)
        match = candidates[0] if len(candidates) == 1 else match_catalog_service(text, services)
        # Ambiguous: keep candidates, withhold a single locked match.
        if len(candidates) > 1:
            match = None
        if match is None and len(candidates) == 1:
            match = candidates[0]
        price_str: str | None = None
        if match is not None:
            for s in services:
                if getattr(s, "id", None) == match.service_id:
                    price = getattr(s, "price", None)
                    if price is not None:
                        price_str = (
                            f"{price:.2f}" if hasattr(price, "__float__") else str(price)
                        )
                    break
        return match, price_str, candidates


def _has_service_signal(text: str, catalog_match: CatalogServiceMatch | None) -> bool:
    if catalog_match is not None:
        return True
    return any(pattern.search(text) for pattern, _ in _SERVICE_PHRASES)


def _refine_with_catalog(
    primary: CustomerIntent,
    confidence: float,
    secondary: list[CustomerIntent],
    text: str,
    catalog_match: CatalogServiceMatch | None,
) -> tuple[CustomerIntent, float, list[CustomerIntent]]:
    """Prefer booking when the customer wants a known shop/service phrase."""
    if not _has_service_signal(text, catalog_match):
        return primary, confidence, secondary
    if primary in _LOCKED_INTENTS:
        return primary, confidence, secondary
    if _ADVISORY.search(text):
        return primary, confidence, secondary
    # "when can I come in for oil change" is availability, not an immediate book.
    if _AVAILABILITY_ASK.search(text):
        if primary != CustomerIntent.CHECK_AVAILABILITY and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.CHECK_AVAILABILITY, max(confidence, 0.88), secondary
    if not _BOOKING_DESIRE.search(text):
        return primary, confidence, secondary

    # "I need an oil change" / "Can I get Brake Inspection" → book that service
    if primary in {
        CustomerIntent.MAINTENANCE_QUESTION,
        CustomerIntent.OTHER,
        CustomerIntent.NEW_CUSTOMER,
        CustomerIntent.RETURNING_CUSTOMER,
    }:
        if primary != CustomerIntent.BOOK_APPOINTMENT and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.BOOK_APPOINTMENT, max(confidence, 0.87), secondary

    return primary, confidence, secondary


def _refine_with_time_preference(
    primary: CustomerIntent,
    confidence: float,
    secondary: list[CustomerIntent],
    entities: dict[str, Any],
    context: AgentContext,
) -> tuple[CustomerIntent, float, list[CustomerIntent]]:
    """Day/time answers after a slot offer continue the booking flow."""
    if primary in _LOCKED_INTENTS:
        return primary, confidence, secondary
    if entities.get("vague_time") and not entities.get("preferred_start"):
        return primary, confidence, secondary
    if not entities.get("preferred_start"):
        return primary, confidence, secondary

    meta = context.metadata or {}
    pending_action = str(meta.get("pending_action") or "")
    # After we asked for a new time on a reschedule hold, a day/clock answer
    # continues the move — never start a fresh booking.
    if pending_action == "reschedule":
        if primary != CustomerIntent.RESCHEDULE and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.RESCHEDULE, max(confidence, 0.9), secondary

    # Already booked in this conversation + new time → move that visit
    # (unless they clearly named a different service for a second booking).
    has_appt = bool(
        meta.get("appointment_id") or meta.get("active_appointment_id")
    )
    if has_appt and _is_same_visit_time_change(entities, meta):
        if primary != CustomerIntent.RESCHEDULE and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.RESCHEDULE, max(confidence, 0.9), secondary

    has_pending = bool(
        meta.get("pending_service")
        or meta.get("pending_service_id")
        or meta.get("slots_offered")
    )
    # Standalone "Tuesday at 2" / follow-up after offer → book that window.
    if primary in {
        CustomerIntent.OTHER,
        CustomerIntent.MAINTENANCE_QUESTION,
        CustomerIntent.NEW_CUSTOMER,
        CustomerIntent.RETURNING_CUSTOMER,
    } and (has_pending or entities.get("requested_service")):
        if primary != CustomerIntent.BOOK_APPOINTMENT and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.BOOK_APPOINTMENT, max(confidence, 0.86), secondary
    return primary, confidence, secondary


def _is_same_visit_time_change(
    entities: dict[str, Any], meta: dict[str, Any]
) -> bool:
    """True when a new time should replace the conversation's existing booking."""
    requested = (
        entities.get("requested_service") or entities.get("service") or ""
    ).strip().casefold()
    if not requested:
        return True
    upcoming = list(meta.get("upcoming_appointments") or [])
    existing = ""
    if upcoming:
        existing = str(upcoming[0].get("service_name") or "").strip().casefold()
    if not existing and meta.get("pending_service"):
        existing = str(meta.get("pending_service") or "").strip().casefold()
    if not existing:
        # We booked something this chat; no catalog name to compare — treat as move.
        return True
    return requested == existing or requested in existing or existing in requested


def _refine_earliest_booking(
    primary: CustomerIntent,
    confidence: float,
    secondary: list[CustomerIntent],
    text: str,
    entities: dict[str, Any],
) -> tuple[CustomerIntent, float, list[CustomerIntent]]:
    """Book earliest/latest opening when the customer asks for first/last available."""
    if not entities.get("prefer_earliest") and not entities.get("prefer_latest"):
        return primary, confidence, secondary
    if primary in {
        CustomerIntent.EMERGENCY,
        CustomerIntent.COMPLAINT,
        CustomerIntent.CANCEL_APPOINTMENT,
        CustomerIntent.RESCHEDULE,
        CustomerIntent.ASK_REPAIR_STATUS,
        CustomerIntent.PRICE_QUESTION,
        CustomerIntent.NEW_CUSTOMER,
    }:
        return primary, confidence, secondary
    wants_book = bool(
        _BOOKING_DESIRE.search(text)
        or re.search(r"\b(book|schedule|reserve|appointment|appt)\b", text, re.I)
    )
    # Pure availability browse ("what's the earliest opening?") stays CHECK.
    is_browse = bool(
        re.search(
            r"\b(what|which|any|do you have|when can|what'?s)\b",
            text,
            re.I,
        )
    )
    if primary == CustomerIntent.CHECK_AVAILABILITY and not wants_book and is_browse:
        return primary, confidence, secondary
    if not wants_book and primary not in {
        CustomerIntent.BOOK_APPOINTMENT,
        CustomerIntent.MAINTENANCE_QUESTION,
        CustomerIntent.CHECK_AVAILABILITY,
        CustomerIntent.OTHER,
    }:
        return primary, confidence, secondary
    # Standalone "today's first" / "last available" → treat as booking preference.
    if primary != CustomerIntent.BOOK_APPOINTMENT and primary not in secondary:
        secondary = [primary, *secondary][:3]
    return CustomerIntent.BOOK_APPOINTMENT, max(confidence, 0.88), secondary


def _refine_cancel_confirmation(
    primary: CustomerIntent,
    confidence: float,
    secondary: list[CustomerIntent],
    text: str,
    context: AgentContext,
) -> tuple[CustomerIntent, float, list[CustomerIntent]]:
    """Treat confirm-cancel / yes-after-cancel-ask as cancel + confirmed."""
    meta = context.metadata or {}
    pending_cancel = bool(meta.get("pending_cancel"))
    pending_action = str(meta.get("pending_action") or "")
    if _AFFIRM_CANCEL.search(text) or (
        (pending_cancel or pending_action == "cancel") and _AFFIRM_BOOK.search(text)
    ):
        if primary != CustomerIntent.CANCEL_APPOINTMENT and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.CANCEL_APPOINTMENT, max(confidence, 0.9), secondary
    if pending_action == "reschedule" and _AFFIRM_BOOK.search(text):
        if primary != CustomerIntent.RESCHEDULE and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.RESCHEDULE, max(confidence, 0.9), secondary
    return primary, confidence, secondary


def _refine_with_name_answer(
    primary: CustomerIntent,
    confidence: float,
    secondary: list[CustomerIntent],
    entities: dict[str, Any],
    context: AgentContext,
) -> tuple[CustomerIntent, float, list[CustomerIntent]]:
    """Name replies during an active booking keep the book flow alive."""
    if primary in _LOCKED_INTENTS:
        return primary, confidence, secondary
    if not entities.get("name"):
        return primary, confidence, secondary
    meta = context.metadata or {}
    pending_action = str(meta.get("pending_action") or "")
    has_pending = bool(
        meta.get("pending_service")
        or meta.get("pending_service_id")
        or meta.get("slots_offered")
        or pending_action == "book"
    )
    if not has_pending:
        return primary, confidence, secondary
    if primary in {
        CustomerIntent.OTHER,
        CustomerIntent.MAINTENANCE_QUESTION,
        CustomerIntent.NEW_CUSTOMER,
        CustomerIntent.RETURNING_CUSTOMER,
    }:
        if primary != CustomerIntent.BOOK_APPOINTMENT and primary not in secondary:
            secondary = [primary, *secondary][:3]
        return CustomerIntent.BOOK_APPOINTMENT, max(confidence, 0.86), secondary
    return primary, confidence, secondary


# Phrases mapped to catalog-friendly service labels (fallback when no shop catalog).
_SERVICE_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bbrake\s+inspection\b", re.I), "Brake Inspection"),
    (re.compile(r"\bbrake\s+repair\b", re.I), "Brake Repair"),
    (re.compile(r"\b(brakes?|brake\s+job|brake\s+pads?)\b", re.I), "brakes"),
    (re.compile(r"\boil\s+change\b", re.I), "Oil Change"),
    (re.compile(r"\btire\s+rotation\b", re.I), "Tire Rotation"),
    (re.compile(r"\b(tires?|tire\s+change)\b", re.I), "tires"),
    (re.compile(r"\b(alignment)\b", re.I), "alignment"),
    (re.compile(r"\b(diagnostic|check\s+engine|scan)\b", re.I), "diagnostic"),
    (re.compile(r"\b(inspection|state\s+inspection)\b", re.I), "inspection"),
    (re.compile(r"\b(battery)\b", re.I), "battery"),
    (re.compile(r"\b(tune[- ]?up)\b", re.I), "tune up"),
]


def _normalize_person_name(raw: str) -> str | None:
    cleaned = " ".join((raw or "").strip().split())
    if not cleaned:
        return None
    parts = cleaned.split()
    if any(p.casefold().rstrip(".,!") in _NAME_STOPWORDS for p in parts):
        return None
    # Title-case lightly so CRM stores a proper name.
    return " ".join(p[:1].upper() + p[1:] if p else p for p in parts)


def _extract_entities(
    text: str,
    catalog_match: CatalogServiceMatch | None = None,
    service_price: str | None = None,
    *,
    service_candidates: list[CatalogServiceMatch] | None = None,
    context: AgentContext | None = None,
) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    if _AFFIRM_BOOK.search(text) or _AFFIRM_CANCEL.search(text):
        entities["booking_confirmed"] = True
    if _AFFIRM_CANCEL.search(text):
        entities["cancel_confirmed"] = True
    if _VAGUE_TIME.search(text):
        entities["vague_time"] = True
    if _EARLIEST_PREF.search(text):
        entities["prefer_earliest"] = True
    if _LATEST_PREF.search(text):
        entities["prefer_latest"] = True
        # Last wins over first when both appear ("first or last" → last).
        if entities.get("prefer_earliest") and re.search(
            r"\b(last|latest)\b", text, re.I
        ):
            entities.pop("prefer_earliest", None)
    phone = re.search(r"(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", text)
    if phone:
        entities["phone"] = phone.group(1)
    vin = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text, re.I)
    if vin:
        entities["vin"] = vin.group(1).upper()
    year = re.search(r"\b(19|20)\d{2}\b", text)
    if year:
        entities["year"] = int(year.group(0))
    mileage = re.search(r"\b(\d{1,3}(?:,\d{3})*|\d+)\s*(?:miles|mi)\b", text, re.I)
    if mileage:
        entities["mileage"] = int(mileage.group(1).replace(",", ""))
    email = re.search(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", text)
    if email:
        entities["email"] = email.group(0).lower()

    name_match = _NAME_EXPLICIT.search(text)
    pending_q = None
    if context is not None:
        pending_q = (context.metadata or {}).get("pending_question")
    if name_match:
        normalized = _normalize_person_name(name_match.group(1))
        if normalized:
            entities["name"] = normalized
    else:
        from app.agents.counselor.persona import is_name_question

        if is_name_question(str(pending_q) if pending_q else None):
            bare = _BARE_NAME.match(text)
            if bare:
                normalized = _normalize_person_name(bare.group(1))
                if normalized:
                    entities["name"] = normalized

    candidates = list(service_candidates or [])
    if len(candidates) > 1:
        entities["service_candidates"] = [c.name for c in candidates[:3]]
        entities["service_needs_disambiguation"] = True
    # Prefer shop catalog match so downstream booking uses real service_id/duration.
    elif catalog_match is not None:
        entities["service"] = catalog_match.name
        entities["requested_service"] = catalog_match.name
        entities["service_id"] = str(catalog_match.service_id)
        entities["duration_minutes"] = catalog_match.duration_minutes
        entities["required_skill"] = catalog_match.skill
        entities["required_bay"] = catalog_match.bay
        entities["service_match_confidence"] = catalog_match.confidence
        if catalog_match.category:
            entities["service_category"] = catalog_match.category
        if service_price is not None:
            entities["service_price"] = service_price
    else:
        for pattern, label in _SERVICE_PHRASES:
            if pattern.search(text):
                entities["service"] = label
                entities["requested_service"] = label
                break

    parsed = parse_preferred_datetime(text)
    if parsed.start is not None and not entities.get("vague_time"):
        entities["preferred_start"] = parsed.start.isoformat()
        entities["time_precision"] = parsed.precision
        # Day / part-of-day must not invent a clock time — ask / offer slots.
        # Earliest/latest preference means pick the first/last free opening in window.
        if parsed.precision in {"day", "part_of_day"} and not (
            entities.get("prefer_earliest") or entities.get("prefer_latest")
        ):
            entities["needs_time"] = True
    if parsed.end is not None and not entities.get("vague_time"):
        entities["preferred_end"] = parsed.end.isoformat()
    # "First/last available" with no day → still prefer edge slot over inventing a clock.
    if (
        entities.get("prefer_earliest") or entities.get("prefer_latest")
    ) and not entities.get("preferred_start"):
        # Default window: remaining shop day today (aligned with day precision).
        from datetime import datetime, timedelta

        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        now = datetime.now(DEFAULT_SHOP_TZ)
        start = now.replace(second=0, microsecond=0)
        end = now.replace(hour=17, minute=0, second=0, microsecond=0)
        if end <= start:
            start = (now + timedelta(days=1)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            end = start.replace(hour=17, minute=0)
        entities["preferred_start"] = start.isoformat()
        entities["preferred_end"] = end.isoformat()
        entities["time_precision"] = "day"
    return entities
