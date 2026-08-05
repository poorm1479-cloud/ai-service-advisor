"""Pure Service Catalog matching for AppointmentDecision (no DB / no ORM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def _has_whole_token(haystack: str, token: str) -> bool:
    """True when token appears as its own word in haystack."""
    if not haystack or not token:
        return False
    return re.search(rf"\b{re.escape(token)}\b", haystack) is not None


def match_catalog_service(
    query: str | None,
    services: Sequence[Any],
    *,
    service_id: UUID | None = None,
) -> CatalogServiceMatch | None:
    """Find the best active catalog service for a customer request.

    Matching order:
    1. Explicit ``service_id`` (UUID lookup)
    2. Exact / substring name match
    3. Skill or category token overlap (ignoring scheduling stop-words)
    """
    active = [s for s in services if getattr(s, "active", True) is not False]
    if not active:
        return None

    if service_id is not None:
        for s in active:
            if getattr(s, "id", None) == service_id:
                return CatalogServiceMatch(
                    service_id=s.id,
                    name=str(s.name),
                    duration_minutes=int(s.duration_minutes),
                    skill=str(getattr(s, "skill", None) or "general"),
                    bay=str(getattr(s, "bay", None) or "general"),
                    confidence=1.0,
                    category=str(getattr(s, "category", "") or ""),
                )
        return None

    q = _norm(query or "")
    if not q:
        return None

    best: CatalogServiceMatch | None = None
    best_score = 0.0
    for s in active:
        name = _norm(str(s.name))
        skill = _norm(str(getattr(s, "skill", "") or ""))
        category = _norm(str(getattr(s, "category", "") or ""))
        score = 0.0
        if q == name or name == q:
            score = 1.0
        elif name and (name in q or q in name):
            score = 0.92
        else:
            tokens = [
                t
                for t in q.split()
                if len(t) > 2 and t not in _STOP_TOKENS
            ]
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
        if score > best_score:
            best_score = score
            best = CatalogServiceMatch(
                service_id=s.id,
                name=str(s.name),
                duration_minutes=int(s.duration_minutes),
                skill=str(getattr(s, "skill", None) or "general"),
                bay=str(getattr(s, "bay", None) or "general"),
                confidence=score,
                category=str(getattr(s, "category", "") or ""),
            )
    if best is None or best_score < 0.55:
        return None
    return best


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
    """
    active = [s for s in services if getattr(s, "active", True) is not False]
    q = _norm(query or "")
    if not q or not active:
        return []

    scored: list[CatalogServiceMatch] = []
    for s in active:
        name = _norm(str(s.name))
        skill = _norm(str(getattr(s, "skill", "") or ""))
        category = _norm(str(getattr(s, "category", "") or ""))
        score = 0.0
        if q == name or name == q:
            score = 1.0
        elif name and (name in q or q in name):
            score = 0.92
        else:
            tokens = [
                t for t in q.split() if len(t) > 2 and t not in _STOP_TOKENS
            ]
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
        if score >= min_score:
            scored.append(
                CatalogServiceMatch(
                    service_id=s.id,
                    name=str(s.name),
                    duration_minutes=int(s.duration_minutes),
                    skill=str(getattr(s, "skill", None) or "general"),
                    bay=str(getattr(s, "bay", None) or "general"),
                    confidence=score,
                    category=str(getattr(s, "category", "") or ""),
                )
            )

    scored.sort(key=lambda m: m.confidence, reverse=True)
    if not scored:
        return []
    if len(scored) == 1:
        return scored[:1]
    top, second = scored[0], scored[1]
    if top.confidence - second.confidence >= ambiguity_gap:
        return [top]
    return scored[:limit]
