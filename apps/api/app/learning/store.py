"""In-memory learning store — tenant isolated."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.learning.models.decision_result import (
    DecisionResultRecord,
    LearningFeedback,
    SuccessPattern,
)


class LearningStorePort(Protocol):
    async def save_result(self, record: DecisionResultRecord) -> DecisionResultRecord: ...

    async def list_results(
        self, shop_id: UUID, *, limit: int = 200, decision_kind: str | None = None
    ) -> list[DecisionResultRecord]: ...

    async def save_feedback(self, feedback: LearningFeedback) -> LearningFeedback: ...

    async def list_feedback(
        self, shop_id: UUID, *, limit: int = 100, source: str | None = None
    ) -> list[LearningFeedback]: ...

    async def save_pattern(self, pattern: SuccessPattern) -> SuccessPattern: ...

    async def list_patterns(self, shop_id: UUID, *, limit: int = 50) -> list[SuccessPattern]: ...


class InMemoryLearningStore:
    def __init__(self) -> None:
        self._results: list[DecisionResultRecord] = []
        self._feedback: list[LearningFeedback] = []
        self._patterns: list[SuccessPattern] = []

    async def save_result(self, record: DecisionResultRecord) -> DecisionResultRecord:
        self._results = [r for r in self._results if r.id != record.id]
        self._results.append(record)
        return record

    async def list_results(
        self, shop_id: UUID, *, limit: int = 200, decision_kind: str | None = None
    ) -> list[DecisionResultRecord]:
        items = [r for r in self._results if r.shop_id == shop_id]
        if decision_kind:
            items = [r for r in items if r.decision_kind == decision_kind]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[:limit]

    async def save_feedback(self, feedback: LearningFeedback) -> LearningFeedback:
        self._feedback = [f for f in self._feedback if f.id != feedback.id]
        self._feedback.append(feedback)
        return feedback

    async def list_feedback(
        self, shop_id: UUID, *, limit: int = 100, source: str | None = None
    ) -> list[LearningFeedback]:
        items = [f for f in self._feedback if f.shop_id == shop_id]
        if source:
            items = [f for f in items if f.source == source]
        items.sort(key=lambda f: f.created_at, reverse=True)
        return items[:limit]

    async def save_pattern(self, pattern: SuccessPattern) -> SuccessPattern:
        self._patterns = [
            p for p in self._patterns if not (p.shop_id == pattern.shop_id and p.pattern_key == pattern.pattern_key)
        ]
        self._patterns.append(pattern)
        return pattern

    async def list_patterns(self, shop_id: UUID, *, limit: int = 50) -> list[SuccessPattern]:
        items = [p for p in self._patterns if p.shop_id == shop_id]
        items.sort(key=lambda p: p.success_rate, reverse=True)
        return items[:limit]
