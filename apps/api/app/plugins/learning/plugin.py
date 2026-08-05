"""Learning Plugin — AI Learning Loop capabilities (decide / analyze only)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.learning.engine import LearningEngine
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext


class LearningPlugin:
    """IPlugin for collecting outcomes, evaluating accuracy, and proposing Decisions."""

    def __init__(self, *, engine: LearningEngine | None = None) -> None:
        self._engine = engine
        self._initialized = False

    def _eng(self) -> LearningEngine:
        if self._engine is None:
            from app.learning.factory import get_learning_runtime

            self._engine = get_learning_runtime().engine
        return self._engine

    def plugin_id(self) -> str:
        return "learning"

    def plugin_name(self) -> str:
        return "AI Learning Loop"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Collect shop interaction outcomes, evaluate decisions, discover patterns, "
            "and propose optimizations via Decision Objects. Never mutates workflows, "
            "prices, or permissions."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.COLLECT_DECISION_RESULT.value,
            Capability.EVALUATE_DECISION.value,
            Capability.LEARN_CUSTOMER_RESPONSE.value,
            Capability.ANALYZE_SUCCESS_PATTERN.value,
            Capability.OPTIMIZE_RECOMMENDATION.value,
            Capability.GENERATE_LEARNING_INSIGHT.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "ai_actions_allowed": False,
            "can_modify_workflows": False,
            "can_change_prices": False,
            "can_change_permissions": False,
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)

        shop_id: UUID | None = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id is required for learning capabilities")

        eng = self._eng()
        source = str(kwargs.get("source") or "").lower()

        if capability == Capability.COLLECT_DECISION_RESULT:
            # Staff / workflow feedback funnel through collector without mutating rules
            if source == "staff":
                return await eng.staff_feedback.submit(
                    shop_id,
                    staff_user_id=kwargs.get("staff_user_id"),
                    rating=kwargs.get("rating"),
                    comment=str(kwargs.get("comment") or kwargs.get("notes") or ""),
                    decision_kind=kwargs.get("decision_kind"),
                    approve_optimization=bool(kwargs.get("approve_optimization") or False),
                    metadata=dict(kwargs.get("metadata") or {}),
                )
            if source == "workflow" or kwargs.get("run") is not None:
                return await eng.workflow_feedback.ingest_run(
                    shop_id,
                    run=kwargs.get("run"),
                    success=kwargs.get("success"),
                    workflow_run_id=kwargs.get("workflow_run_id"),
                    notes=str(kwargs.get("notes") or ""),
                )
            return await eng.collect_decision_result(
                shop_id,
                decision_kind=str(kwargs.get("decision_kind") or "unknown"),
                outcome_kind=kwargs.get("outcome_kind") or "conversation",
                success=bool(kwargs.get("success", True)),
                customer_id=kwargs.get("customer_id")
                or (context.customer_id if context else None),
                workflow_run_id=kwargs.get("workflow_run_id"),
                correlation_id=kwargs.get("correlation_id"),
                score=kwargs.get("score"),
                notes=str(kwargs.get("notes") or ""),
                metadata=dict(kwargs.get("metadata") or {}),
            )

        if capability == Capability.EVALUATE_DECISION:
            return await eng.evaluate_decision(
                shop_id,
                decision_kind=kwargs.get("decision_kind"),
                limit=int(kwargs.get("limit") or 200),
            )

        if capability == Capability.LEARN_CUSTOMER_RESPONSE:
            return await eng.learn_customer_response(
                shop_id,
                customer_id=kwargs.get("customer_id")
                or (context.customer_id if context else None),
                positive=bool(kwargs.get("positive", True)),
                comment=str(kwargs.get("comment") or kwargs.get("notes") or ""),
                decision_kind=kwargs.get("decision_kind"),
                rating=kwargs.get("rating"),
                metadata=dict(kwargs.get("metadata") or {}),
            )

        if capability == Capability.ANALYZE_SUCCESS_PATTERN:
            return await eng.analyze_success_pattern(
                shop_id, limit=int(kwargs.get("limit") or 300)
            )

        if capability == Capability.OPTIMIZE_RECOMMENDATION:
            return await eng.optimize_recommendation(
                shop_id,
                target=str(kwargs.get("target") or "recommendations"),
                limit=int(kwargs.get("limit") or 300),
            )

        if capability == Capability.GENERATE_LEARNING_INSIGHT:
            return await eng.generate_learning_insight(shop_id)

        raise ValueError(f"Unknown learning capability: {capability}")
