"""Shared reschedule / move-visit phrasing for intent + counselor.

Keep one pattern so conversation intent and mid-call desire checks stay aligned.
"""

from __future__ import annotations

import re
from typing import Any

# Appointment-like nouns (spoken / abbreviated).
_APPT = r"(?:appointment|appt|booking|reservation|visit|slot)"
_TIME = r"(?:time|date|day|schedule)"

# Verbs that mean "move an existing booking" (incl. STT: reset ≈ reschedule).
_MOVE_VERBS = (
    r"(?:re-?schedule|reschedule|rebook|re-?book|rearrange|re-?arrange|"
    r"reset|re-?set|redo|re-?do|replace|re-?place|reshuffle|re-?shuffle|"
    r"revise|rework|readjust|re-?adjust|"
    r"move|switch|modify|update|edit|adjust|shift|delay|postpone|"
    r"bump|slide)"
)

# Job / catalog service nouns for service-type swap on an existing visit.
# Keep separate from pure time phrases so "change the time" is not a service ask.
# Bare "service" must not match "service time/date/…" (time move, not job swap).
_NOT_SERVICE_TIME = (
    r"(?!\s+(?:time|date|day|hour|hours|schedule|appointment|appt|"
    r"booking|reservation|visit|slot|window)\b)"
)
_SERVICE_OBJ = (
    rf"(?:service(?:\s+type|\s+kind)?{_NOT_SERVICE_TIME}|"
    r"type\s+of\s+service|kind\s+of\s+service|service\s+category|"
    r"repair(?:\s+type)?|job|work\s*order|package|"
    r"what\s+(?:i|we|you)\s+(?:booked|scheduled|reserved))"
)
_SERVICE_SWAP_VERBS = (
    r"(?:change|switch|swap|update|modify|replace|alter|revise|edit|"
    r"correct|fix|adjust)"
)
_SERVICE_ALT = r"(?:different|another|new|other|wrong|incorrect|right)"
# Optional "both" between verb and object: "change both the service type…".
_BOTH = r"(?:both\s+)?"
# Soft joiners for compound service+time: and / as well as / plus / also.
_AND = r"(?:and|&|\+|plus|as\s+well\s+as|also|along\s+with|together\s+with)"
# Service-side nouns for service+time compounds (broader than _SERVICE_OBJ alone).
_COMPOUND_SVC = (
    r"(?:service(?:\s+type|\s+kind|\s+category)?|type\s+of\s+service|"
    r"kind\s+of\s+service|repair(?:\s+type)?|job|work\s*order|package|"
    r"what\s+(?:i|we)\s+(?:booked|scheduled))"
)
# Time-side nouns for compounds (clock / day / when).
_COMPOUND_WHEN = (
    rf"(?:{_TIME}|{_APPT}(?:\s+{_TIME})?|"
    r"when|timing|slot|window|hour|hours|"
    r"day\s+and\s+time|date\s+and\s+time|time\s+and\s+date)"
)
# Soft lead-ins: want/need/can we …
_COMPOUND_LEAD = (
    r"(?:(?:i\s+)?(?:want|need|like|prefer|trying)\s+to\s+|"
    r"(?:can|could|may)\s+(?:i|we)\s+|"
    r"(?:let'?s|please)\s+|"
    r"(?:i'?d\s+like\s+to\s+)|"
    r"(?:is\s+it\s+(?:possible|ok|okay)\s+to\s+))?"
)

# Shared alternation body for service-type swap (reschedule + dedicated check).
_SERVICE_TYPE_CHANGE_BODY = (
    # change / switch / swap the service (type)
    rf"(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+"
    rf"{_BOTH}(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"{_SERVICE_OBJ}\b|"
    # switch services / swap services
    rf"(?:switch|swap|change)\s+services\b|"
    # different / another / wrong service
    rf"{_SERVICE_ALT}\s+{_SERVICE_OBJ}\b|"
    # noun phrases
    rf"service\s+type\s+change|"
    rf"service\s+kind\s+change|"
    rf"type\s+of\s+service\s+change|"
    rf"kind\s+of\s+service\s+change|"
    rf"service\s+change\b|"
    rf"(?:service|job|repair)\s+(?:swap|switch|upgrade|downgrade)\b|"
    # change what service / what I booked
    rf"(?:change|switch|swap|update|modify)\s+what\s+"
    rf"(?:service|job|repair|i\s+booked|we\s+booked|i\s+scheduled)\b|"
    # booked the wrong / not the right service
    rf"booked\s+(?:the\s+)?(?:wrong|incorrect)\s+(?:service|job|repair|thing)\b|"
    rf"(?:got|have)\s+(?:the\s+)?(?:wrong|incorrect)\s+(?:service|job|repair)\b|"
    rf"not\s+(?:the\s+)?(?:right|correct)\s+(?:service|job|repair)\b|"
    rf"not\s+(?:the\s+)?service\s+i\s+(?:wanted|booked|meant|asked\s+for)\b|"
    # actually need a different service / something else done
    rf"(?:actually|instead)\s+(?:i\s+)?(?:need|want|like)\s+"
    rf"(?:a\s+|an\s+|the\s+)?(?:different|another|other)\s+"
    rf"(?:service|job|repair)\b|"
    rf"(?:need|want|like)\s+(?:a\s+|an\s+)?"
    rf"(?:different|another|other)\s+(?:service|job|repair)(?:\s+type)?\b|"
    rf"(?:need|want|like)\s+something\s+(?:else|different)\s+"
    rf"(?:done|instead|for\s+(?:my\s+)?(?:{_APPT}))\b|"
    # go with / do a different service instead
    rf"(?:go\s+with|do|get|have)\s+(?:a\s+|an\s+)?"
    rf"(?:different|another|other)\s+(?:service|job|repair)\b|"
    rf"(?:rather|instead)\s+(?:do|get|have|book)\s+(?:a\s+|an\s+)?"
    rf"(?:different|another)\s+(?:service|job|repair)\b|"
    # change service on / for my appointment (not oil change)
    rf"(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+"
    rf"{_BOTH}(?:the\s+|my\s+)?service\s+(?:on|for|of)\s+"
    rf"(?:my\s+|the\s+|our\s+)?(?:{_APPT})\b|"
    # change appointment *service* / service type (job swap, not clock)
    rf"(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+"
    rf"{_BOTH}(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"(?:{_APPT})\s+(?:service(?:\s+type|\s+kind)?|repair(?:\s+type)?|job)\b|"
    # switch to a different service (destination may follow)
    rf"(?:switch|change|swap|convert)\s+to\s+(?:a\s+|an\s+)?"
    rf"(?:different|another|other|new)\s+(?:service|job|repair)\b|"
    # STT / casual: update my booking service, revise service type
    # (not "update the service time" — that is a clock move)
    rf"(?:update|revise|edit|correct)\s+(?:my\s+|the\s+)?"
    rf"(?:booking\s+)?service(?:\s+type|\s+kind)?{_NOT_SERVICE_TIME}\b|"
    rf"make\s+(?:it|that)\s+(?:a\s+|an\s+)?"
    rf"(?:different|another)\s+(?:service|job|repair)\b|"
    # ── Compound: change both service type AND time (spoken synonyms) ──
    # change|swap|update both the service (type) and the time/date/day
    rf"{_COMPOUND_LEAD}(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+{_BOTH}"
    rf"(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"{_COMPOUND_SVC}\s+{_AND}\s+(?:my\s+|the\s+|our\s+|also\s+the\s+)?"
    rf"{_COMPOUND_WHEN}\b|"
    # change both the time and the service (type)
    rf"{_COMPOUND_LEAD}(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+{_BOTH}"
    rf"(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"{_COMPOUND_WHEN}\s+{_AND}\s+(?:my\s+|the\s+|our\s+|also\s+the\s+)?"
    rf"{_COMPOUND_SVC}\b|"
    # change the service type as well / too / also (with time stated elsewhere
    # in the same phrase is handled by _AND joins above — do not treat bare
    # "change the time too" as a service swap)
    rf"{_COMPOUND_LEAD}(?<!\boil\s){_SERVICE_SWAP_VERBS}\s+{_BOTH}"
    rf"(?:my\s+|the\s+)?"
    rf"{_COMPOUND_SVC}\s+(?:as\s+well|too|also)\b|"
    # move the time and change the service (mixed verbs, either order)
    rf"(?:move|shift|adjust|update)\s+(?:my\s+|the\s+)?"
    rf"{_COMPOUND_WHEN}\s+{_AND}\s+"
    rf"(?:{_SERVICE_SWAP_VERBS}\s+)?(?:my\s+|the\s+)?{_COMPOUND_SVC}\b|"
    rf"(?:{_SERVICE_SWAP_VERBS})\s+(?:my\s+|the\s+)?"
    rf"{_COMPOUND_SVC}\s+{_AND}\s+"
    rf"(?:(?:move|shift|adjust|update|change)\s+)?(?:my\s+|the\s+)?"
    rf"{_COMPOUND_WHEN}\b|"
    # different service and different/new time
    rf"(?:{_SERVICE_ALT}\s+){_COMPOUND_SVC}\s+{_AND}\s+"
    rf"(?:a\s+|an\s+|the\s+|a\s+)?(?:{_SERVICE_ALT}\s+)?{_COMPOUND_WHEN}\b|"
    rf"(?:{_SERVICE_ALT}\s+){_COMPOUND_WHEN}\s+{_AND}\s+"
    rf"(?:a\s+|an\s+|the\s+|a\s+)?(?:{_SERVICE_ALT}\s+)?{_COMPOUND_SVC}\b|"
    # need/want a different service and time (no explicit change verb)
    rf"(?:need|want|like|prefer)\s+(?:a\s+|an\s+|the\s+)?"
    rf"(?:{_SERVICE_ALT}\s+)?{_COMPOUND_SVC}\s+{_AND}\s+"
    rf"(?:a\s+|an\s+|the\s+)?(?:{_SERVICE_ALT}\s+)?{_COMPOUND_WHEN}\b|"
    # change what and when / service and when
    rf"(?:change|switch|update|modify)\s+what\s+{_AND}\s+when\b|"
    rf"(?:change|switch|update|modify)\s+(?:the\s+)?service\s+{_AND}\s+when\b|"
    # rebook / redo with different service and time
    rf"(?:re-?book|rebook|redo|re-?do|re-?schedule|reschedule)\s+"
    rf"(?:with\s+)?(?:a\s+|an\s+)?(?:{_SERVICE_ALT}\s+)?"
    rf"{_COMPOUND_SVC}\s+{_AND}\s+(?:a\s+|an\s+)?(?:{_SERVICE_ALT}\s+)?"
    rf"{_COMPOUND_WHEN}\b|"
    # change everything / whole booking (service implied with visit context)
    rf"(?:change|update|modify|redo)\s+(?:the\s+)?"
    rf"(?:whole|entire|full)\s+(?:{_APPT}|booking|thing)\b|"
    rf"change\s+(?:it\s+)?all\b|"
    # noun-style compounds
    rf"(?:service(?:\s+type)?|job|repair)\s+{_AND}\s+"
    rf"(?:{_TIME}|when)\s+change\b|"
    rf"(?:{_TIME}|when)\s+{_AND}\s+"
    rf"(?:service(?:\s+type)?|job|repair)\s+change\b|"
    rf"(?:service(?:\s+type)?|job)\s+{_AND}\s+time\s+(?:update|swap|switch)\b|"
    rf"time\s+{_AND}\s+(?:service(?:\s+type)?|job)\s+(?:update|swap|switch)\b|"
    rf"both\s+(?:the\s+)?(?:service(?:\s+type)?|job)\s+{_AND}\s+"
    rf"(?:the\s+)?(?:{_TIME}|when)\b|"
    rf"both\s+(?:the\s+)?(?:{_TIME}|when)\s+{_AND}\s+"
    rf"(?:the\s+)?(?:service(?:\s+type)?|job)\b|"
    # "not just the time — the service too" / "service not just the time"
    rf"(?:not\s+just|not\s+only)\s+(?:the\s+)?"
    rf"(?:{_TIME}|service(?:\s+type)?|job)\s*"
    rf"(?:[,—\-–]\s*|\s+)(?:but\s+)?(?:also\s+)?(?:the\s+)?"
    rf"(?:service(?:\s+type)?|job|{_TIME})"
    rf"(?:\s+(?:too|as\s+well))?\b|"
    # dual different objects without strong verb: "new service and new time"
    rf"(?:new|different|another)\s+(?:service|job|repair)\s+{_AND}\s+"
    rf"(?:a\s+|an\s+)?(?:new|different|another)\s+(?:time|day|date|slot)\b"
)

# Exclude "oil change …" so maintenance booking is not treated as a reschedule.
# Cover common spoken variants + STT slips (reset, redo, re set, …).
RESCHEDULE_PATTERN = re.compile(
    rf"\b("
    # Bare / explicit verbs (reset alone is a common reschedule stand-in)
    rf"re-?schedule|reschedule|rebook|re-?book|rearrange|re-?arrange|"
    rf"reset|re-?set|redo|re-?do|replace|re-?place|reshuffle|re-?shuffle|"
    rf"rework|revise|"
    rf"(?:is\s+it\s+)?(?:possible|ok|okay)\s+to\s+"
    rf"(?:change|reschedule|re-?schedule|reset|re-?set|replace|re-?place|"
    rf"move|redo)\b|"
    rf"(?:want|need|like|trying)\s+to\s+"
    rf"(?:reset|re-?set|replace|re-?place|reschedule|re-?schedule|rebook|"
    rf"redo|re-?do|rearrange|change|move|switch|adjust|modify|update)\b|"
    # Verb + visit / time object
    rf"{_MOVE_VERBS}\s+(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"(?:{_APPT}|{_TIME})(?:\s+(?:time|date|day))?|"
    rf"{_MOVE_VERBS}\s+(?:it|that)(?:\s+(?:please|too))?|"
    # Push / pull timing (both word orders)
    rf"push\s+(?:my\s+|the\s+)?(?:{_APPT}|it)\s+"
    rf"(?:back|forward|later|earlier)|"
    rf"push\s+(?:it\s+)?(?:back|forward)|"
    rf"(?:move|switch|shift|slide)\s+(?:it\s+)?"
    rf"(?:back|forward|to\s+(?:a\s+)?(?:different|another)\s+{_TIME})|"
    # Change appointment / booking / visit (not oil change)
    rf"(?<!\boil\s)change\s+(?:my\s+|the\s+)?"
    rf"(?:{_APPT})(?:\s+(?:time|date|day|service(?:\s+type|\s+kind)?))?|"
    rf"(?<!\boil\s)change\s+(?:my\s+|the\s+)?(?:{_TIME})"
    rf"(?:\s+of\s+(?:my\s+)?(?:{_APPT}))?|"
    # "change the service time" — time object after "service" (not job swap)
    rf"(?<!\boil\s)(?:change|switch|modify|update|edit|adjust|move)\s+"
    rf"(?:my\s+|the\s+|our\s+|this\s+|that\s+)?"
    rf"service\s+(?:(?:{_APPT})\s+)?(?:{_TIME})(?:\s+of\s+(?:my\s+)?(?:{_APPT}))?|"
    rf"(?:service|appointment|booking)\s+(?:{_TIME})\s+change|"
    rf"(?<!\boil\s)change\s+(?:it|that)(?:\s+(?:please|too))?|"
    rf"(?<!\boil\s)change\s+to\s+(?:a\s+)?(?:different|another|new)\s+"
    rf"(?:{_TIME})|"
    # Service-type swap synonyms (shared body)
    rf"{_SERVICE_TYPE_CHANGE_BODY}|"
    # Noun-style
    rf"(?:{_APPT})(?:\s+time)?\s+change|"
    rf"time\s+change|"
    # Different / another / new day|time
    rf"(?:different|another|new)\s+(?:{_TIME})"
    rf"(?:\s+for\s+(?:my\s+)?(?:{_APPT}))?|"
    rf"(?:pick|choose|do|come(?:\s+in)?)\s+(?:on\s+)?(?:a\s+)?"
    rf"(?:different|another)\s+(?:{_TIME})|"
    rf"come\s+(?:in\s+)?(?:on\s+)?(?:a\s+)?(?:different|another)\s+(?:day|time)|"
    # Set a new time for existing plan
    rf"set\s+(?:a\s+|my\s+|the\s+)?new\s+(?:{_TIME})|"
    rf"set\s+(?:my\s+|the\s+)?(?:{_APPT})\s+(?:to|for)\b|"
    # Availability conflict with existing visit
    rf"(?:can'?t|cannot|can\s+not)\s+make\s+it|"
    rf"(?:can'?t|cannot|can\s+not)\s+come\s+(?:in\b|then\b|that\s+day|that\s+time)|"
    rf"(?:that|this|the)\s+(?:{_TIME})\s+(?:does\s+not|doesn'?t)\s+work|"
    rf"doesn'?t\s+work\s+for\s+me|"
    rf"something\s+came\s+up|"
    rf"(?:later|earlier)\s+(?:time|appointment|slot)|"
    rf"(?:later|earlier)\s+(?:in\s+the\s+day|that\s+day)|"
    # Soft asks
    rf"(?:can\s+we|can\s+i|could\s+we|could\s+i|let'?s)\s+"
    rf"(?:reset|re-?set|replace|re-?place|reschedule|re-?schedule|rebook|"
    rf"redo|re-?do|move|change|switch|adjust|modify|swap)\b"
    rf")\b",
    re.I,
)

# Weaker cues promoted only when conversation already has a visit / reschedule hold.
_WEAK_RESCHEDULE = re.compile(
    r"\b("
    r"reset|re-?set|replace|re-?place|redo|re-?do|reshuffle|"
    r"rework|revise|adjust|shift|delay|postpone|"
    r"not\s+(?:that|this)\s+(?:day|time|date)|"
    r"won'?t\s+work|"
    r"unavailable\s+(?:then|that\s+day|that\s+time)|"
    r"conflict|"
    r"busy\s+(?:then|that\s+day)|"
    r"need\s+to\s+(?:change|move|reset|replace|adjust)|"
    # Soft service-swap hints (only with existing-visit promotion)
    r"wrong\s+(?:one|service|job)|"
    r"something\s+else\s+(?:instead|done)|"
    r"not\s+what\s+i\s+(?:booked|wanted|meant)"
    r")\b",
    re.I,
)


def looks_like_reschedule_text(text: str | None) -> bool:
    """True when free text strongly suggests moving an existing appointment."""
    return bool(text and RESCHEDULE_PATTERN.search(text))


def looks_like_weak_reschedule_text(text: str | None) -> bool:
    """Softer cue — only use with an existing appointment context."""
    return bool(text and _WEAK_RESCHEDULE.search(text))


# Service-type swap on an existing visit (not necessarily a time move).
_SERVICE_TYPE_CHANGE = re.compile(
    rf"\b({_SERVICE_TYPE_CHANGE_BODY})\b",
    re.I,
)


def looks_like_service_type_change(text: str | None) -> bool:
    """True when free text asks to swap the job, not (only) the clock time."""
    return bool(text and _SERVICE_TYPE_CHANGE.search(text))


def has_existing_visit_context(metadata: dict[str, Any] | None) -> bool:
    """True when memory/enrichment points at a booked (or pending) visit."""
    meta = metadata or {}
    if meta.get("appointment_id") or meta.get("active_appointment_id"):
        return True
    if str(meta.get("pending_action") or "") in {"reschedule", "cancel"}:
        return True
    if meta.get("pending_cancel"):
        return True
    upcoming = meta.get("upcoming_appointments") or []
    return bool(upcoming)
