"""AI Service Advisor — digital service advisor (decide only, never mutates)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.advisor.communication.service import AdvisorCommunicationService
from app.plugins.advisor.customer.service import AdvisorCustomerService
from app.plugins.advisor.estimate.service import AdvisorEstimateService
from app.plugins.advisor.followup.service import AdvisorFollowUpService
from app.plugins.advisor.models import AdvisorContext, AdvisorPlan
from app.plugins.advisor.repair.service import AdvisorRepairService
from app.plugins.advisor.vehicle.service import AdvisorVehicleService
from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext


class AdvisorPlugin:
    """IPlugin — AI Service Advisor manages lifecycle via Decision Objects only."""

    def __init__(
        self,
        *,
        customer: AdvisorCustomerService | None = None,
        vehicle: AdvisorVehicleService | None = None,
        estimate: AdvisorEstimateService | None = None,
        repair: AdvisorRepairService | None = None,
        followup: AdvisorFollowUpService | None = None,
        communication: AdvisorCommunicationService | None = None,
    ) -> None:
        self._customer = customer or AdvisorCustomerService()
        self._vehicle = vehicle or AdvisorVehicleService()
        self._estimate = estimate or AdvisorEstimateService()
        self._repair = repair or AdvisorRepairService()
        self._followup = followup or AdvisorFollowUpService()
        self._communication = communication or AdvisorCommunicationService()
        self._queue: list[dict[str, Any]] = []
        self._initialized = False

    def plugin_id(self) -> str:
        return "advisor"

    def plugin_name(self) -> str:
        return "AI Service Advisor"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Digital Service Advisor for the complete customer service lifecycle. "
            "Returns Decision Objects only — Workflow executes all business actions."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.ANALYZE_CONVERSATION.value,
            Capability.ANALYZE_CUSTOMER.value,
            Capability.ANALYZE_VEHICLE.value,
            Capability.GENERATE_REPAIR_RECOMMENDATION.value,
            Capability.GENERATE_ESTIMATE_SUMMARY.value,
            Capability.GENERATE_CUSTOMER_EXPLANATION.value,
            Capability.GENERATE_APPROVAL_REQUEST.value,
            Capability.GENERATE_REPAIR_UPDATE.value,
            Capability.GENERATE_FOLLOW_UP.value,
            Capability.GENERATE_MAINTENANCE_REMINDER.value,
            Capability.GENERATE_REVIEW_REQUEST.value,
            Capability.GENERATE_RETENTION_PLAN.value,
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
            "queue_size": len(self._queue),
        }

    def build_context(self, **kwargs: Any) -> AdvisorContext:
        shop_id = kwargs["shop_id"]
        return AdvisorContext(
            shop_id=shop_id,
            conversation_id=kwargs.get("conversation_id"),
            customer_id=kwargs.get("customer_id"),
            vehicle_id=kwargs.get("vehicle_id"),
            channel=kwargs.get("channel"),
            inbound_text=kwargs.get("inbound_text") or kwargs.get("text") or kwargs.get("content"),
            intent=kwargs.get("intent"),
            customer=kwargs.get("customer"),
            vehicle=kwargs.get("vehicle"),
            repair_history=list(kwargs.get("repair_history") or []),
            conversation_history=list(kwargs.get("conversation_history") or []),
            inspection_results=list(kwargs.get("inspection_results") or []),
            photos=list(kwargs.get("photos") or []),
            mileage=kwargs.get("mileage"),
            appointments=list(kwargs.get("appointments") or []),
            technician_notes=list(kwargs.get("technician_notes") or []),
            revenue_opportunities=list(kwargs.get("revenue_opportunities") or []),
            metadata=dict(kwargs.get("metadata") or {}),
        )

    def advise(self, ctx: AdvisorContext) -> AdvisorPlan:
        """Full lifecycle advise pass — Decision Objects only."""
        decisions: list[Any] = []
        decisions.extend(self._customer.analyze(ctx))
        vehicle_recs = self._vehicle.analyze(ctx)
        decisions.extend(vehicle_recs)
        from app.agents.decisions.types import RepairRecommendationDecision

        recs = [d for d in vehicle_recs if isinstance(d, RepairRecommendationDecision)]
        decisions.extend(self._estimate.generate_summary(ctx, recommendations=recs))
        decisions.extend(self._estimate.generate_approval_request(ctx))
        decisions.extend(self._repair.generate_update(ctx))
        decisions.extend(self._followup.generate_follow_up(ctx))
        decisions.extend(self._communication.generate_customer_explanation(ctx, recommendations=recs))

        notes = self._advisor_notes(ctx, decisions)
        priority = self._queue_priority(decisions)
        suggestions = [getattr(d, "rationale", "") or str(getattr(d, "kind", "")) for d in decisions]
        dash = self.dashboard_snapshot(ctx, decisions, priority=priority)
        self._enqueue(ctx, decisions, priority=priority, notes=notes)
        return AdvisorPlan(
            decisions=decisions,
            advisor_notes=notes,
            queue_priority=priority,
            suggestions=[s for s in suggestions if s],
            dashboard=dash,
        )

    def dashboard_snapshot(
        self, ctx: AdvisorContext, decisions: list[Any], *, priority: str = "normal"
    ) -> dict[str, Any]:
        return {
            "advisor_queue": list(self._queue)[-20:],
            "pending_customer_replies": [
                d
                for d in decisions
                if getattr(getattr(d, "kind", None), "value", None) == "customer_communication"
            ],
            "pending_approvals": [
                d
                for d in decisions
                if getattr(getattr(d, "kind", None), "value", None) == "approval_request"
            ],
            "high_value_customers": [
                d
                for d in decisions
                if getattr(getattr(d, "kind", None), "value", None) == "retention"
                and getattr(d, "priority", "") in {"high", "urgent"}
            ],
            "urgent_repairs": [
                d
                for d in decisions
                if getattr(getattr(d, "kind", None), "value", None) == "repair_recommendation"
                and getattr(d, "urgency", "") in {"high", "urgent"}
            ],
            "follow_up_queue": [
                d
                for d in decisions
                if getattr(getattr(d, "kind", None), "value", None)
                in {"maintenance_reminder", "review_request"}
            ],
            "ai_suggestions": [
                getattr(d, "plain_language", None)
                or getattr(d, "message_body", None)
                or getattr(d, "body", None)
                or getattr(d, "plan", None)
                for d in decisions
            ],
            "conversation_id": ctx.conversation_id,
            "priority": priority,
        }

    def _enqueue(
        self, ctx: AdvisorContext, decisions: list[Any], *, priority: str, notes: str
    ) -> None:
        self._queue.append(
            {
                "shop_id": str(ctx.shop_id),
                "conversation_id": ctx.conversation_id,
                "customer_id": str(ctx.customer_id) if ctx.customer_id else None,
                "priority": priority,
                "decision_count": len(decisions),
                "notes": notes,
                "kinds": [
                    getattr(getattr(d, "kind", None), "value", str(type(d).__name__))
                    for d in decisions
                ],
            }
        )
        if len(self._queue) > 200:
            self._queue = self._queue[-200:]

    def _advisor_notes(self, ctx: AdvisorContext, decisions: list[Any]) -> str:
        parts = [
            f"Intent={ctx.intent or 'unknown'}",
            f"Channel={ctx.channel or 'n/a'}",
            f"Decisions={len(decisions)}",
        ]
        if ctx.inbound_text:
            parts.append(f"Inbound={(ctx.inbound_text[:80])}")
        return " | ".join(parts)

    def _queue_priority(self, decisions: list[Any]) -> str:
        order = {"urgent": 3, "high": 2, "normal": 1, "low": 0}
        best = 1
        for d in decisions:
            for attr in ("urgency", "priority"):
                val = getattr(d, attr, None)
                if val in order:
                    best = max(best, order[val])
        for k, v in order.items():
            if v == best:
                return k
        return "normal"

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
            if context.conversation_id and not kwargs.get("conversation_id"):
                kwargs["conversation_id"] = context.conversation_id

        ctx = self.build_context(**kwargs)

        if capability == Capability.ANALYZE_CONVERSATION:
            memory_ctx: dict[str, Any] = {}
            if ctx.shop_id is not None:
                try:
                    from app.plugins.advisor.memory_context import load_advisor_memory_context

                    memory_ctx = await load_advisor_memory_context(
                        ctx.shop_id,
                        customer_id=ctx.customer_id,
                        vehicle_id=ctx.vehicle_id,
                        query=ctx.inbound_text,
                    )
                    ctx.metadata["memory_context"] = memory_ctx
                except Exception:  # noqa: BLE001
                    memory_ctx = {}
            plan = self.advise(ctx)
            return {
                "decisions": plan.decisions,
                "advisor_notes": plan.advisor_notes,
                "queue_priority": plan.queue_priority,
                "suggestions": plan.suggestions,
                "dashboard": plan.dashboard,
                "memory_context": memory_ctx,
            }

        if capability == Capability.ANALYZE_CUSTOMER:
            return {"decisions": self._customer.analyze(ctx)}

        if capability == Capability.ANALYZE_VEHICLE:
            return {"decisions": self._vehicle.analyze(ctx)}

        if capability == Capability.GENERATE_REPAIR_RECOMMENDATION:
            return {"decisions": self._vehicle.analyze(ctx)}

        if capability == Capability.GENERATE_ESTIMATE_SUMMARY:
            recs = self._vehicle.analyze(ctx)
            from app.agents.decisions.types import RepairRecommendationDecision

            only = [d for d in recs if isinstance(d, RepairRecommendationDecision)]
            return {"decisions": self._estimate.generate_summary(ctx, recommendations=only)}

        if capability == Capability.GENERATE_CUSTOMER_EXPLANATION:
            recs = self._vehicle.analyze(ctx)
            from app.agents.decisions.types import RepairRecommendationDecision

            only = [d for d in recs if isinstance(d, RepairRecommendationDecision)]
            return {
                "decisions": self._communication.generate_customer_explanation(
                    ctx, recommendations=only
                )
            }

        if capability == Capability.GENERATE_APPROVAL_REQUEST:
            return {"decisions": self._estimate.generate_approval_request(ctx)}

        if capability == Capability.GENERATE_REPAIR_UPDATE:
            return {"decisions": self._repair.generate_update(ctx)}

        if capability == Capability.GENERATE_FOLLOW_UP:
            return {"decisions": self._followup.generate_follow_up(ctx)}

        if capability == Capability.GENERATE_MAINTENANCE_REMINDER:
            return {
                "decisions": self._followup.generate_maintenance_reminder(
                    ctx,
                    service=str(kwargs.get("service") or "service"),
                    due_mileage=kwargs.get("due_mileage"),
                )
            }

        if capability == Capability.GENERATE_REVIEW_REQUEST:
            return {"decisions": self._followup.generate_review_request(ctx)}

        if capability == Capability.GENERATE_RETENTION_PLAN:
            return {"decisions": self._customer.analyze(ctx)}

        raise ValueError(f"Unknown advisor capability: {capability}")
