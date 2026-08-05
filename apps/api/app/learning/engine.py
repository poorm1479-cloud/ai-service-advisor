"""Learning Loop engine — analyze outcomes, propose Decisions only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.decisions.types import LearningFeedbackDecision
from app.learning.collector import LearningCollector
from app.learning.evaluator import LearningEvaluator
from app.learning.feedback.customer import CustomerFeedbackService
from app.learning.feedback.staff import StaffFeedbackService
from app.learning.feedback.workflow import WorkflowFeedbackService
from app.learning.models.decision_result import LearningInsight
from app.learning.optimizer import LearningOptimizer
from app.learning.store import InMemoryLearningStore, LearningStorePort


class LearningEngine:
    def __init__(self, *, store: LearningStorePort | None = None) -> None:
        self._store = store or InMemoryLearningStore()
        self.collector = LearningCollector(self._store)
        self.evaluator = LearningEvaluator(self._store)
        self.optimizer = LearningOptimizer(self._store)
        self.customer_feedback = CustomerFeedbackService(self._store, self.collector)
        self.staff_feedback = StaffFeedbackService(self._store)
        self.workflow_feedback = WorkflowFeedbackService(self._store, self.collector)

    @property
    def store(self) -> LearningStorePort:
        return self._store

    async def collect_decision_result(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        record = await self.collector.collect_decision_result(shop_id, **kwargs)
        return {"result": record.to_dict(), "ai_actions_allowed": False}

    async def evaluate_decision(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return await self.evaluator.evaluate_decision(shop_id, **kwargs)

    async def learn_customer_response(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return await self.customer_feedback.learn_customer_response(shop_id, **kwargs)

    async def analyze_success_pattern(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return await self.optimizer.analyze_success_pattern(shop_id, **kwargs)

    async def optimize_recommendation(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return await self.optimizer.optimize_recommendation(shop_id, **kwargs)

    async def generate_learning_insight(self, shop_id: UUID) -> dict[str, Any]:
        metrics = await self.evaluator.metrics(shop_id)
        patterns = await self._store.list_patterns(shop_id, limit=5)
        recs = [
            "Continue collecting outcome samples across appointments and repairs",
        ]
        if patterns:
            recs.insert(
                0,
                f"Promote pattern '{patterns[0].pattern_key}' after staff review",
            )
        if metrics["decision_accuracy"] < 0.5 and metrics["sample_count"] >= 5:
            recs.append("Decision accuracy below 50% — request staff review of recent failures")
        insight = LearningInsight(
            shop_id=shop_id,
            title="Learning Loop Insight",
            summary=(
                f"Accuracy={metrics['decision_accuracy']:.0%} "
                f"over {metrics['sample_count']} outcomes"
            ),
            metrics=metrics,
            recommendations=recs,
            confidence=min(0.9, 0.3 + metrics["sample_count"] * 0.02),
        )
        decision = LearningFeedbackDecision(
            source="system",
            summary=insight.summary,
            insights=recs,
            metrics=metrics,
            requires_review=True,
            rationale=insight.summary,
        )
        return {
            "insight": insight.to_dict(),
            "decision": decision,
            "decisions": [decision],
            "ai_actions_allowed": False,
        }

    async def dashboard_metrics(self, shop_id: UUID) -> dict[str, Any]:
        return await self.evaluator.metrics(shop_id)

    def feedback_decision(
        self,
        *,
        source: str,
        summary: str,
        rating: float | None = None,
        insights: list[str] | None = None,
    ) -> LearningFeedbackDecision:
        return LearningFeedbackDecision(
            source=source,
            summary=summary,
            rating=rating,
            insights=list(insights or []),
            requires_review=True,
            rationale=summary,
        )
