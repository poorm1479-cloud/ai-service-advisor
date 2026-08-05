"""Phase 21 — AI Learning Loop.

Analyzes real shop outcomes and proposes improvements via Decision Objects.
AI never autonomously changes workflows, prices, or permissions.
"""

from app.learning.factory import (
    LearningRuntime,
    build_learning_runtime,
    get_learning_runtime,
    reset_learning_runtime,
)

__all__ = [
    "LearningRuntime",
    "build_learning_runtime",
    "get_learning_runtime",
    "reset_learning_runtime",
]
