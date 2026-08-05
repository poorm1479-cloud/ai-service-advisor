"""Customer response feedback intake."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.learning.models.decision_result import LearningFeedback, OutcomeKind
from app.learning.store import LearningStorePort


class CustomerFeedbackService:
    def __init__(self, store: LearningStorePort, collector: Any) -> None:
        self._store = store
        self._collector = collector

    async def learn_customer_response(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        positive: bool = True,
        comment: str = "",
        decision_kind: str | None = None,
        rating: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fb = LearningFeedback(
            id=uuid4(),
            shop_id=shop_id,
            source="customer",
            rating=rating if rating is not None else (1.0 if positive else 0.0),
            comment=comment,
            customer_id=customer_id,
            decision_kind=decision_kind,
            metadata=dict(metadata or {}),
        )
        await self._store.save_feedback(fb)
        result = await self._collector.collect_decision_result(
            shop_id,
            decision_kind=decision_kind or "customer_response",
            outcome_kind=OutcomeKind.CUSTOMER_RESPONSE,
            success=positive,
            customer_id=customer_id,
            notes=comment or ("positive" if positive else "negative"),
            metadata={"source": "customer", **dict(metadata or {})},
        )
        return {
            "feedback": fb.to_dict(),
            "result": result.to_dict(),
            "ai_actions_allowed": False,
        }
