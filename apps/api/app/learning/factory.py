"""DI factory for AI Learning Loop."""

from __future__ import annotations

from dataclasses import dataclass

from app.learning.engine import LearningEngine
from app.learning.store import InMemoryLearningStore, LearningStorePort

_runtime: LearningRuntime | None = None


@dataclass(slots=True)
class LearningRuntime:
    engine: LearningEngine
    store: LearningStorePort


def build_learning_runtime(*, store: LearningStorePort | None = None) -> LearningRuntime:
    resource = store or InMemoryLearningStore()
    engine = LearningEngine(store=resource)
    return LearningRuntime(engine=engine, store=resource)


def get_learning_runtime() -> LearningRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_learning_runtime()
    return _runtime


def reset_learning_runtime() -> None:
    global _runtime
    _runtime = None
