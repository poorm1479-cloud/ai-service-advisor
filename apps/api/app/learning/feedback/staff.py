"""Staff feedback intake — review signal for learning, not auto rule changes."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.learning.models.decision_result import LearningFeedback
from app.learning.store import LearningStorePort


class StaffFeedbackService:
    def __init__(self, store: LearningStorePort) -> None:
        self._store = store

    async def submit(
        self,
        shop_id: UUID,
        *,
        staff_user_id: UUID | None = None,
        rating: float | None = None,
        comment: str = "",
        decision_kind: str | None = None,
        approve_optimization: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fb = LearningFeedback(
            id=uuid4(),
            shop_id=shop_id,
            source="staff",
            rating=rating,
            comment=comment,
            staff_user_id=staff_user_id,
            decision_kind=decision_kind,
            metadata={
                **dict(metadata or {}),
                "approve_optimization": bool(approve_optimization),
            },
        )
        await self._store.save_feedback(fb)
        return {
            "feedback": fb.to_dict(),
            "auto_applied": False,
            "note": "Staff feedback recorded; Workflow review required for any rule change",
            "ai_actions_allowed": False,
        }
