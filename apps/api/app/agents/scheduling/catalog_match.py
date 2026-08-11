"""Pure Service Catalog matching for AppointmentDecision (no DB / no ORM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

# Common chat words that appear inside service names (e.g. "change" in "Oil Change")
# must not alone trigger a catalog match on reschedule/time phrases.
_STOP_TOKENS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "have",
        "need",
        "want",
        "like",
        "book",
        "make",
        "get",
        "set",
        "can",
        "could",
        "would",
        "please",
        "just",
        "also",
        "about",
        "into",
        "your",
        "my",
        "our",
        "any",
        "some",
        "what",
        "when",
        "where",
        "which",
        "how",
        "are",
        "is",
        "was",
        "were",
        "been",
        "being",
        "do",
        "does",
        "did",
        "doing",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "or",
        "an",
        "a",
        "i",
        "me",
        "we",
        "you",
        "they",
        "them",
        "appointment",
        "appt",
        "booking",
        "reservation",
        "schedule",
        "scheduled",
        "reschedule",
        "rescheduled",
        "reset",
        "replace",
        "redo",
        "rebook",
        "rearrange",
        "adjust",
        "postpone",
        "delay",
        "cancel",
        "cancelled",
        "canceled",
        "change",
        "changed",
        "move",
        "moved",
        "switch",
        "time",
        "times",
        "day",
        "days",
        "date",
        "dates",
        "slot",
        "slots",
        "opening",
        "openings",
        "available",
        "availability",
        "visit",
        "come",
        "service",
        "services",
        "repair",
        "repairs",
        "shop",
        "today",
        "tomorrow",
        "tonight",
        "morning",
        "afternoon",
        "evening",
        "next",
        "week",
        "different",
        "another",
        "new",
        "prefer",
        "preferred",
        "works",
        "work",
        "best",
        "help",
        "thanks",
        "thank",
        "yes",
        "yeah",
        "yep",
        "okay",
        "sure",
        "confirm",
    }
)


@dataclass(slots=True, frozen=True)
class CatalogServiceMatch:
    """Resolved catalog service for an AppointmentDecision."""

    service_id: UUID
    name: str
    duration_minutes: int
    skill: str
    bay: str
    confidence: float
    category: str = ""
    price: Decimal = Decimal("0")


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def _has_whole_token(haystack: str, token: str) -> bool:
    """True when token appears as its own word in haystack."""
    if not haystack or not token:
        return False
    return re.search(rf"\b{re.escape(token)}\b", haystack) is not None


def extract_service_switch_target(text: str | None) -> str | None:
    """Phrase after switch/change-to (destination service), if any.

    Used so "change my oil change to brake repair" picks Brake Repair instead of
    treating both catalog hits as ambiguous.
    """
    if not text:
        return None
    _svc = (
        r"service(?:\s+type|\s+kind)?|type\s+of\s+service|kind\s+of\s+service|"
        r"job|work(?:\s*order)?|repair(?:\s+type)?|package|appointment|visit|booking"
    )
    _verb = r"switch|change|update|modify|convert|replace|make|swap|alter|revise|edit|correct"
    patterns = (
        # change/switch/update … to X
        # Optional object may end mid-phrase ("service type") so allow \s* before
        # "to" — without it "change the service type to brakes" never matches.
        re.compile(
            rf"\b(?:{_verb})\s+"
            r"(?:it\s+|that\s+)?"
            r"(?:(?:my|the|our|this|that)\s+)?"
            rf"(?:{_svc})?"
            r"(?:\s+from\s+.+?)?"
            r"\s*(?:to|into)\s+(?:a\s+|an\s+|the\s+)?(?P<target>.+?)"
            r"(?=\s+(?:instead|rather|for|on|at|please|tomorrow|today|tonight|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"next|this)\b|[.!,?]|$)",
            re.I,
        ),
        # X instead (of Y)
        re.compile(
            r"\b(?:to|for)\s+(?:a\s+|an\s+|the\s+)?(?P<target>.+?)\s+instead\b",
            re.I,
        ),
        re.compile(
            r"\binstead\s+(?:of\s+(?:a\s+|an\s+|the\s+)?\S+\s+)?"
            r"(?:do|get|book|schedule)?\s*(?:a\s+|an\s+|the\s+)?"
            r"(?P<target>[a-z][a-z0-9\s\-]{2,40})\b",
            re.I,
        ),
        # "I want brake repair instead of oil change"
        re.compile(
            r"\b(?:want|need|like|prefer|do|get)\s+"
            r"(?:a\s+|an\s+|the\s+)?(?P<target>.+?)\s+instead\b",
            re.I,
        ),
        # "actually I need brake repair" / "go with tire rotation instead"
        re.compile(
            r"\b(?:actually|instead)\s+(?:i\s+)?(?:need|want|like|get|do)\s+"
            r"(?:a\s+|an\s+|the\s+)?(?P<target>.+?)"
            r"(?=\s+(?:instead|rather|please|tomorrow|today|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|[.!,?]|$)",
            re.I,
        ),
        # "make it a brake repair" / "make that tire rotation"
        re.compile(
            r"\bmake\s+(?:it|that)\s+(?:a\s+|an\s+|the\s+)?(?P<target>.+?)"
            r"(?=\s+(?:instead|rather|please|tomorrow|today)\b|[.!,?]|$)",
            re.I,
        ),
    )
    for pattern in patterns:
        m = pattern.search(text)
        if not m:
            continue
        target = " ".join((m.group("target") or "").strip().split())
        # Drop trailing day/time leftovers the non-lookahead path may leave.
        target = re.sub(
            r"\b(on|at|for|please|tomorrow|today|tonight|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
            "",
            target,
            flags=re.I,
        ).strip(" .,!?;:-")
        if len(target) >= 3:
            return target
    return None


def _score_service_against_query(s: Any, q: str) -> float:
    """Score one catalog row against a normalized query string."""
    name = _norm(str(s.name))
    skill = _norm(str(getattr(s, "skill", "") or ""))
    category = _norm(str(getattr(s, "category", "") or ""))
    score = 0.0
    if q == name or name == q:
        score = 1.0
    elif name and (name in q or q in name):
        score = 0.92
    else:
        tokens = [t for t in q.split() if len(t) > 2 and t not in _STOP_TOKENS]
        hits = 0
        for t in tokens:
            if (
                _has_whole_token(name, t)
                or _has_whole_token(skill, t)
                or _has_whole_token(category, t)
            ):
                hits += 1
        if hits:
            score = min(0.88, 0.55 + 0.1 * hits)
        skill_compact = skill.replace(" ", "")
        q_compact = q.replace(" ", "")
        if skill_compact and len(skill_compact) > 3 and skill_compact in q_compact:
            score = max(score, 0.85)
    return score


def _match_from_score(s: Any, score: float) -> CatalogServiceMatch:
    raw_price = getattr(s, "price", None)
    try:
        price = Decimal(str(raw_price if raw_price is not None else 0))
    except Exception:  # noqa: BLE001 — bad catalog row must not break matching
        price = Decimal("0")
    return CatalogServiceMatch(
        service_id=s.id,
        name=str(s.name),
        duration_minutes=int(s.duration_minutes),
        skill=str(getattr(s, "skill", None) or "general"),
        bay=str(getattr(s, "bay", None) or "general"),
        confidence=score,
        category=str(getattr(s, "category", "") or ""),
        price=price,
    )


def _match_by_name(query: str | None, active: Sequence[Any]) -> CatalogServiceMatch | None:
    q = _norm(query or "")
    if not q:
        return None
    best: CatalogServiceMatch | None = None
    best_score = 0.0
    for s in active:
        score = _score_service_against_query(s, q)
        if score > best_score:
            best_score = score
            best = _match_from_score(s, score)
    if best is None or best_score < 0.55:
        return None
    return best


def match_catalog_service(
    query: str | None,
    services: Sequence[Any],
    *,
    service_id: UUID | None = None,
) -> CatalogServiceMatch | None:
    """Find the best active catalog service for a customer request.

    Matching order:
    1. Strong name match (preferred over a conflicting pinned service_id —
       voice/SMS reschedule often carries the *old* visit id while naming the
       replacement job)
    2. Explicit ``service_id`` (UUID lookup)
    3. Weaker name / skill / category overlap
    """
    active = [s for s in services if getattr(s, "active", True) is not False]
    if not active:
        return None

    name_match = _match_by_name(query, active)

    id_match: CatalogServiceMatch | None = None
    if service_id is not None:
        for s in active:
            if getattr(s, "id", None) == service_id:
                id_match = _match_from_score(s, 1.0)
                break
        if id_match is None and name_match is None:
            return None

    # Strong name for a *different* service beats a stale appointment service_id.
    if (
        name_match is not None
        and name_match.confidence >= 0.9
        and (
            id_match is None
            or name_match.service_id != id_match.service_id
        )
    ):
        return name_match
    if id_match is not None:
        return id_match
    return name_match


def find_catalog_service_candidates(
    query: str | None,
    services: Sequence[Any],
    *,
    limit: int = 3,
    min_score: float = 0.55,
    ambiguity_gap: float = 0.08,
) -> list[CatalogServiceMatch]:
    """Return top catalog matches when the query is ambiguous.

    A single clear winner (gap above runner-up) yields one match; otherwise
    up to ``limit`` close candidates for the counselor to disambiguate.

    When the utterance includes switch/change-to wording, prefer the destination
    phrase as a single match so "oil change → brake repair" is not ambiguous.
    """
    active = [s for s in services if getattr(s, "active", True) is not False]
    if not active:
        return []

    switch_q = extract_service_switch_target(query)
    if switch_q:
        switch_match = _match_by_name(switch_q, active)
        if switch_match is not None and switch_match.confidence >= 0.85:
            return [switch_match]

    q = _norm(query or "")
    if not q:
        return []

    scored: list[CatalogServiceMatch] = []
    for s in active:
        score = _score_service_against_query(s, q)
        if score >= min_score:
            scored.append(_match_from_score(s, score))

    scored.sort(key=lambda m: m.confidence, reverse=True)
    if not scored:
        return []
    if len(scored) == 1:
        return scored[:1]
    top, second = scored[0], scored[1]
    if top.confidence - second.confidence >= ambiguity_gap:
        return [top]
    return scored[:limit]
