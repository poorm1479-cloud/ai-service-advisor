"""Workflow Decision Executor — sole component allowed to apply AI Decisions.

AI modules propose Decision objects. This executor calls CRM, Scheduling,
Marketing, Memory, and publishes domain events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agents.base.agent import AgentContext
from app.agents.crm.models import CrmUpdateResult, TimelineEntry
from app.agents.customer.models import CustomerProfile, CustomerResolveResult
from app.agents.decisions.types import (
    AppointmentDecision,
    ApprovalRequestDecision,
    CampaignRecommendationDecision,
    ContactTimingDecision,
    CrmUpdateDecision,
    CustomerCommunicationDecision,
    CustomerDecision,
    CustomerExplanationDecision,
    CustomerMemoryDecision,
    CustomerRetentionDecision,
    CustomerValueDecision,
    Decision,
    EscalationDecision,
    EstimateExplanationDecision,
    FollowUpDecision,
    InspectionAnalysisDecision,
    InventoryRiskDecision,
    KnowledgeRetrievalDecision,
    LearningFeedbackDecision,
    MaintenanceReminderDecision,
    MarketingDecision,
    MemoryDecision,
    OptimizationDecision,
    PartCostDecision,
    PartsAvailabilityDecision,
    PatternDiscoveryDecision,
    PurchaseRecommendationDecision,
    RepairReadinessDecision,
    RepairRecommendationDecision,
    RepairStatusDecision,
    RetentionDecision,
    RevenueDecision,
    RevenueOpportunityDecision,
    ReviewRequestDecision,
    SafetyAlertDecision,
    ServiceRecommendationDecision,
    ShopPreferenceDecision,
    SummaryDecision,
    VehicleDecision,
    VehicleMemoryDecision,
)
from app.agents.marketing.models import MarketingActionResult
from app.agents.scheduling.models import AppointmentRecord, Reminder, SchedulingResult, TimeSlot
from app.agents.vehicle.models import VehicleRecord, VehicleResolveResult
from app.workflows.enums import DomainEventType
from app.workflows.monitoring import WorkflowMonitor

logger = logging.getLogger("asa.workflows.decision_executor")


@dataclass(slots=True)
class DecisionPorts:
    """Business-module ports injected for execution (never held by AI agents for writes)."""

    customer_directory: Any | None = None
    vehicle_directory: Any | None = None
    scheduling_store: Any | None = None
    crm_store: Any | None = None
    marketing_dispatcher: Any | None = None
    memory_service: Any | None = None
    # Preferred CRM access — Workflow must use ICrmPlugin, never raw CRM services
    crm_plugin: Any | None = None
    # Preferred Scheduling access — Workflow must use ISchedulingPlugin
    scheduling_plugin: Any | None = None
    # Preferred Conversation access — Workflow must use IConversationPlugin / ConversationId
    conversation_plugin: Any | None = None
    # Preferred Revenue access — Workflow must use IRevenuePlugin
    revenue_plugin: Any | None = None
    # Preferred Advisor access — decide-only plugin; Workflow applies its Decisions
    advisor_plugin: Any | None = None
    # Preferred Inspection Intelligence — decide-only; Workflow applies its Decisions
    inspection_plugin: Any | None = None
    # Preferred Inventory Intelligence — decide-only analysis; Workflow reserves/orders
    inventory_plugin: Any | None = None


@dataclass
class DecisionExecutionResult:
    applied: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    customer_result: CustomerResolveResult | None = None
    vehicle_result: VehicleResolveResult | None = None
    scheduling_result: SchedulingResult | None = None
    crm_result: CrmUpdateResult | None = None
    marketing_results: list[MarketingActionResult] = field(default_factory=list)
    escalations: list[dict[str, Any]] = field(default_factory=list)
    revenue_result: dict[str, Any] | None = None
    advisor_results: list[dict[str, Any]] = field(default_factory=list)


class DecisionExecutor:
    """Interpret AI Decisions and perform all business side effects."""

    def __init__(
        self,
        *,
        monitor: WorkflowMonitor | None = None,
        emit_fn: Any | None = None,
        escalate_fn: Any | None = None,
    ) -> None:
        self._monitor = monitor or WorkflowMonitor()
        self._emit = emit_fn
        self._escalate = escalate_fn

    def _plugin_context(self, shop_id: UUID, context: AgentContext) -> Any:
        from app.plugins.framework.context import PluginContext

        return PluginContext.from_agent_context(
            context,
            shop_id=shop_id,
            customer_id=context.customer_id,
            vehicle_id=context.vehicle_id,
            correlation_id=context.correlation_id,
            conversation_id=context.conversation_id,
        )

    def _conversation_uuid(self, context: AgentContext) -> UUID | None:
        if not context.conversation_id:
            return None
        try:
            return UUID(str(context.conversation_id))
        except (ValueError, TypeError):
            return None

    async def _record_conversation_decision(
        self,
        decision: Decision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> None:
        cid = self._conversation_uuid(context)
        if cid is None:
            return
        try:
            from app.plugins.framework.capability import Capability

            kind = str(getattr(decision, "kind", type(decision).__name__))
            payload: dict[str, Any] = {}
            try:
                from dataclasses import asdict, is_dataclass

                if is_dataclass(decision):
                    raw = asdict(decision)
                    payload = {
                        k: (str(v) if isinstance(v, UUID) else v)
                        for k, v in raw.items()
                        if k != "kind"
                    }
            except Exception:  # noqa: BLE001
                payload = {"repr": repr(decision)}
            await self._invoke_cap(
                Capability.UPDATE_CONVERSATION.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                conversation_id=cid,
                decision={
                    "kind": kind,
                    "rationale": getattr(decision, "rationale", None),
                    "payload": payload,
                },
                customer_id=context.customer_id,
                vehicle_id=context.vehicle_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("conversation.decision_record_skipped", exc_info=True)

    async def _apply_repair_recommendation(
        self,
        decision: RepairRecommendationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Record advisor recommendation on the CRM timeline only.

        Do not write RepairHistory here — that table is completed service work.
        Booking / recommending a job must not appear as past repair history.
        """
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                summary = decision.plain_language or decision.title or decision.service_type
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="repair_recommendation",
                    summary=summary,
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.repair_timeline_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"service_type": decision.service_type, "title": decision.title}

    async def _apply_estimate_explanation(
        self,
        decision: EstimateExplanationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        body = decision.plain_language or decision.summary
        if customer_id and body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.estimate_comm_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.ESTIMATE_SENT,
            shop_id,
            {
                "customer_id": str(customer_id) if customer_id else None,
                "amount": str(decision.amount),
                "summary": decision.summary,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"amount": str(decision.amount), "summary": decision.summary}

    async def _apply_approval_request(
        self,
        decision: ApprovalRequestDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.message_body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.message_body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.approval_comm_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.ESTIMATE_SENT,
            shop_id,
            {
                "customer_id": str(customer_id) if customer_id else None,
                "amount": str(decision.amount),
                "services": list(decision.services),
                "approval_requested": True,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"services": list(decision.services), "amount": str(decision.amount)}

    async def _apply_repair_status(
        self,
        decision: RepairStatusDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.message_body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.message_body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.status_comm_skipped", exc_info=True)
        event = (
            DomainEventType.REPAIR_FINISHED
            if decision.status in {"ready", "completed"}
            else DomainEventType.REPAIR_STARTED
        )
        await self._emit_event(
            event,
            shop_id,
            {
                "customer_id": str(customer_id) if customer_id else None,
                "status": decision.status,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"status": decision.status}

    async def _apply_maintenance_reminder(
        self,
        decision: MaintenanceReminderDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        mkt = MarketingDecision(
            action_type="maintenance_reminder",
            channel=decision.channel,
            customer_id=decision.customer_id or context.customer_id,
            template="maintenance_reminder",
            body=decision.message_body,
            context={
                "service": decision.service,
                "due_mileage": decision.due_mileage,
            },
            rationale=decision.rationale,
        )
        try:
            result = await self._apply_marketing(mkt, ports)
            out_marketing = {
                "dispatched": getattr(result, "dispatched", False),
                "action_type": result.action_type,
            }
        except Exception:  # noqa: BLE001
            out_marketing = {"dispatched": False}
        await self._emit_event(
            DomainEventType.MAINTENANCE_REMINDER_REQUESTED,
            shop_id,
            {
                "customer_id": str(decision.customer_id or context.customer_id or ""),
                "service": decision.service,
                "due_mileage": decision.due_mileage,
                "channel": decision.channel,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"service": decision.service, "marketing": out_marketing}

    async def _apply_review_request(
        self,
        decision: ReviewRequestDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        mkt = MarketingDecision(
            action_type="review_request",
            channel=decision.channel,
            customer_id=decision.customer_id or context.customer_id,
            template="review_request",
            body=decision.message_body,
            rationale=decision.rationale,
        )
        try:
            result = await self._apply_marketing(mkt, ports)
            out = {"dispatched": getattr(result, "dispatched", False)}
        except Exception:  # noqa: BLE001
            out = {"dispatched": False}
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return out

    async def _apply_retention(
        self,
        decision: RetentionDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="retention",
                    summary=decision.plan or decision.rationale,
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.retention_timeline_skipped", exc_info=True)
        if context.conversation_id:
            try:
                await self._invoke_cap(
                    Capability.UPDATE_CONVERSATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    conversation_id=UUID(str(context.conversation_id)),
                    priority=decision.priority,
                    decision={
                        "kind": "retention",
                        "plan": decision.plan,
                        "risk_score": decision.risk_score,
                        "actions": list(decision.actions),
                    },
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.retention_conversation_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"plan": decision.plan, "risk_score": decision.risk_score}

    async def _apply_customer_communication(
        self,
        decision: CustomerCommunicationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.comm_skipped", exc_info=True)
        if context.conversation_id and decision.body:
            try:
                await self._invoke_cap(
                    Capability.UPDATE_CONVERSATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    conversation_id=UUID(str(context.conversation_id)),
                    message={
                        "sender": "ai_assistant",
                        "receiver": "customer",
                        "channel": decision.channel,
                        "content": decision.body,
                        "direction": "outbound",
                        "intent": decision.intent,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.debug("advisor.comm_conversation_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"channel": decision.channel, "body": decision.body[:200]}

    async def _apply_inspection_analysis(
        self,
        decision: InspectionAnalysisDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.condition_summary:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="inspection_analysis",
                    summary=decision.condition_summary,
                )
            except Exception:  # noqa: BLE001
                logger.debug("inspection.analysis_timeline_skipped", exc_info=True)
        if decision.safety_count > 0:
            await self._emit_event(
                DomainEventType.HUMAN_ESCALATION_REQUESTED,
                shop_id,
                {
                    "reason": "inspection_safety_findings",
                    "inspection_id": str(decision.inspection_id) if decision.inspection_id else None,
                    "safety_count": decision.safety_count,
                    "urgency": decision.urgency,
                },
                context.correlation_id,
            )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "condition_summary": decision.condition_summary,
            "finding_count": decision.finding_count,
            "safety_count": decision.safety_count,
        }

    async def _apply_safety_alert(
        self,
        decision: SafetyAlertDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        body = decision.plain_language or decision.issue or decision.title
        if customer_id and body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("inspection.safety_comm_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.HUMAN_ESCALATION_REQUESTED,
            shop_id,
            {
                "reason": "safety_alert",
                "title": decision.title,
                "severity": decision.severity,
                "urgent": decision.urgent,
                "inspection_id": str(decision.inspection_id) if decision.inspection_id else None,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"title": decision.title, "severity": decision.severity, "urgent": decision.urgent}

    async def _apply_customer_explanation(
        self,
        decision: CustomerExplanationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.plain_language:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.plain_language,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("inspection.explanation_comm_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "template": decision.template,
            "category": decision.category,
            "title": decision.title,
        }

    async def _apply_follow_up(
        self,
        decision: FollowUpDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.message_body:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.message_body,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("inspection.followup_comm_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.REMINDER_SCHEDULED,
            shop_id,
            {
                "reason": decision.reason,
                "customer_id": str(customer_id) if customer_id else None,
                "scheduled_at": decision.scheduled_at.isoformat() if decision.scheduled_at else None,
                "inspection_id": str(decision.inspection_id) if decision.inspection_id else None,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"reason": decision.reason, "priority": decision.priority}

    async def _apply_parts_availability(
        self,
        decision: PartsAvailabilityDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        reserved = None
        if decision.reserve_recommended and decision.sufficient and decision.sku:
            try:
                reserved = await self._invoke_cap(
                    Capability.RESERVE_PART.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    sku=decision.sku,
                    quantity=decision.quantity_needed,
                    repair_id=decision.repair_id,
                    customer_id=decision.customer_id or context.customer_id,
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.reserve_skipped", exc_info=True)
        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="parts_availability",
                    summary=(
                        f"{decision.part_name or decision.sku}: "
                        f"{'available' if decision.sufficient else 'short'} "
                        f"({decision.quantity_available}/{decision.quantity_needed})"
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.availability_timeline_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "sku": decision.sku,
            "sufficient": decision.sufficient,
            "reserved": reserved,
        }

    async def _apply_inventory_risk(
        self,
        decision: InventoryRiskDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.message:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="inventory_risk",
                    summary=decision.message,
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.risk_timeline_skipped", exc_info=True)
        if decision.risk_level in {"high", "urgent"} or decision.delay_days >= 3:
            await self._emit_event(
                DomainEventType.HUMAN_ESCALATION_REQUESTED,
                shop_id,
                {
                    "reason": "inventory_risk",
                    "risk_level": decision.risk_level,
                    "delay_days": decision.delay_days,
                    "missing_skus": list(decision.missing_skus),
                },
                context.correlation_id,
            )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "risk_level": decision.risk_level,
            "delay_days": decision.delay_days,
            "missing_skus": list(decision.missing_skus),
        }

    async def _apply_purchase_recommendation(
        self,
        decision: PurchaseRecommendationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Record purchase recommendation — never executes the purchase."""
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        summary = (
            f"Purchase recommended: {decision.quantity}x {decision.part_name or decision.sku} "
            f"via {decision.supplier_name or 'supplier'} "
            f"(~${decision.estimated_cost}, lead {decision.lead_time_days}d)"
        )
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="purchase_recommendation",
                    summary=summary,
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.purchase_timeline_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.REVENUE_OPPORTUNITY_DETECTED,
            shop_id,
            {
                "kind": "parts_purchase",
                "sku": decision.sku,
                "quantity": decision.quantity,
                "estimated_cost": str(decision.estimated_cost),
                "supplier_name": decision.supplier_name,
                "lead_time_days": decision.lead_time_days,
                # Explicit: recommendation only — not an executed PO
                "executed": False,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"sku": decision.sku, "quantity": decision.quantity, "executed": False}

    async def _apply_repair_readiness(
        self,
        decision: RepairReadinessDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id and decision.customer_message:
            try:
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.customer_message,
                    direction="outbound",
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.readiness_comm_skipped", exc_info=True)
        if decision.schedule_adjustment == "delay" and decision.delay_days > 0:
            await self._emit_event(
                DomainEventType.REMINDER_SCHEDULED,
                shop_id,
                {
                    "reason": "parts_delay",
                    "delay_days": decision.delay_days,
                    "blocking_parts": list(decision.blocking_parts),
                    "customer_id": str(customer_id) if customer_id else None,
                    # Scheduling update signal — AI did not mutate appointments
                    "schedule_adjustment": decision.schedule_adjustment,
                },
                context.correlation_id,
            )
        elif decision.ready:
            await self._emit_event(
                DomainEventType.REPAIR_FINISHED,
                shop_id,
                {
                    "phase": "parts_ready",
                    "ready": True,
                    "parts_cost_total": str(decision.parts_cost_total),
                    "customer_id": str(customer_id) if customer_id else None,
                },
                context.correlation_id,
            )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ready": decision.ready,
            "delay_days": decision.delay_days,
            "schedule_adjustment": decision.schedule_adjustment,
        }

    async def _apply_part_cost(
        self,
        decision: PartCostDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="part_cost",
                    summary=(
                        f"{decision.part_name or decision.sku}: "
                        f"{decision.quantity}x @ ${decision.unit_cost} = ${decision.line_cost}"
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.debug("inventory.cost_timeline_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"sku": decision.sku, "line_cost": str(decision.line_cost)}

    async def _apply_revenue(
        self,
        decision: RevenueDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        # Prefer listing/detecting opportunities via Capability Registry (no direct revenue_intel)
        result = await self._invoke_cap(
            Capability.DETECT_REVENUE_OPPORTUNITY.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            run_analysis=False,
            emit_workflow_events=True,
            limit=50,
        )
        upsells = await self._invoke_cap(
            Capability.GENERATE_UPSELL_RECOMMENDATIONS.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            limit=20,
        )
        if context.customer_id is not None:
            try:
                await self._invoke_cap(
                    Capability.CALCULATE_CUSTOMER_LIFETIME_VALUE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=context.customer_id,
                )
            except Exception:  # noqa: BLE001
                pass

        await self._record_conversation_decision(decision, shop_id, ports, context)
        await self._emit_event(
            DomainEventType.REVENUE_UPDATED,
            shop_id,
            {
                "conversation_id": context.conversation_id,
                "predicted_revenue": str(decision.predicted_revenue),
                "lost_customer_risk": decision.lost_customer_risk,
                "opportunity_count": (
                    result.get("count") if isinstance(result, dict) else None
                ),
            },
            context.correlation_id,
        )
        return {
            "detect": result,
            "upsells": upsells,
            "decision": {
                "predicted_revenue": str(decision.predicted_revenue),
                "lost_customer_risk": decision.lost_customer_risk,
                "upsell_count": len(decision.upsell_opportunities),
                "declined_count": len(decision.declined_estimates),
                "maintenance_count": len(decision.maintenance_reminders),
            },
        }

    async def _apply_summary(
        self,
        decision: SummaryDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> None:
        cid = self._conversation_uuid(context)
        if cid is None:
            return
        from app.plugins.framework.capability import Capability

        await self._invoke_cap(
            Capability.CONVERSATION_SUMMARY.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            conversation_id=cid,
            enrich=True,
            persist=True,
            summary=decision.summary,
            owner_summary=decision.summary,
            highlights=list(decision.highlights),
            action_items=list(decision.action_items),
            text=context.metadata.get("inbound_text"),
        )
        await self._invoke_cap(
            Capability.UPDATE_CONVERSATION.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            conversation_id=cid,
            decision={
                "kind": "summary",
                "summary": decision.summary,
                "highlights": list(decision.highlights),
                "action_items": list(decision.action_items),
            },
            customer_id=context.customer_id,
            vehicle_id=context.vehicle_id,
        )

    @staticmethod
    def _shop_local_date(when: datetime):
        from app.agents.intent.datetime_parse import DEFAULT_SHOP_TZ

        if when.tzinfo is None:
            return when.replace(tzinfo=DEFAULT_SHOP_TZ).date()
        return when.astimezone(DEFAULT_SHOP_TZ).date()

    @classmethod
    def _filter_slots_for_soft_preference(
        cls,
        slots: list[TimeSlot],
        *,
        preferred_start: datetime,
        preferred_end: datetime | None,
    ) -> list[TimeSlot]:
        """Keep openings on the preferred shop-local day / window."""
        day = cls._shop_local_date(preferred_start)
        same_day = [s for s in slots if cls._shop_local_date(s.start) == day]
        if preferred_end is None:
            return same_day or slots
        # part-of-day window with light slack (matches SchedulingAgent)
        window_start = preferred_start - timedelta(hours=1)
        window_end = preferred_end + timedelta(hours=1)
        in_window = [
            s for s in same_day if window_start <= s.start < window_end
        ]
        return in_window or same_day or slots

    async def _invoke_cap(
        self,
        capability: str,
        *,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
        **kwargs: Any,
    ) -> Any:
        """Invoke via Capability Registry only — no direct plugin imports."""
        from app.plugins.framework.factory import invoke_capability

        return await invoke_capability(
            capability,
            context=self._plugin_context(shop_id, context),
            ports=ports,
            shop_id=shop_id,
            **kwargs,
        )

    async def apply(
        self,
        *,
        shop_id: UUID,
        decisions: list[Decision],
        ports: DecisionPorts,
        context: AgentContext | None = None,
        correlation_id: str | None = None,
    ) -> DecisionExecutionResult:
        ctx = context or AgentContext(shop_id=shop_id, correlation_id=correlation_id or str(uuid4()))
        result = DecisionExecutionResult()
        self._monitor.record_orchestration("apply_decisions")

        for decision in decisions:
            try:
                await self._apply_one(decision, shop_id=shop_id, ports=ports, context=ctx, out=result)
            except Exception as exc:  # noqa: BLE001
                logger.exception("decision.apply_failed kind=%s", getattr(decision, "kind", type(decision)))
                result.errors.append(str(exc))

        return result

    async def _apply_one(
        self,
        decision: Decision,
        *,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
        out: DecisionExecutionResult,
    ) -> None:
        if isinstance(decision, CustomerDecision):
            out.customer_result = await self._apply_customer(decision, shop_id, ports, context)
            out.applied.append({"kind": "customer", "action": decision.action})
        elif isinstance(decision, VehicleDecision):
            out.vehicle_result = await self._apply_vehicle(decision, shop_id, ports, context)
            out.applied.append({"kind": "vehicle", "action": decision.action})
        elif isinstance(decision, AppointmentDecision):
            out.scheduling_result = await self._apply_appointment(decision, shop_id, ports, context)
            out.applied.append({"kind": "appointment", "action": decision.action})
        elif isinstance(decision, CrmUpdateDecision):
            out.crm_result = await self._apply_crm(decision, shop_id, ports, context)
            out.applied.append({"kind": "crm"})
        elif isinstance(decision, MarketingDecision):
            mr = await self._apply_marketing(decision, ports)
            out.marketing_results.append(mr)
            out.applied.append({"kind": "marketing", "action_type": decision.action_type})
        elif isinstance(decision, EscalationDecision):
            entry = await self._apply_escalation(decision, shop_id, ports, context)
            out.escalations.append(entry)
            out.applied.append({"kind": "escalation", "escalate": decision.escalate})
        elif isinstance(decision, MemoryDecision):
            await self._apply_memory(decision, shop_id, ports, context)
            out.applied.append({"kind": "memory", "facts": len(decision.facts)})
        elif isinstance(decision, SummaryDecision):
            await self._apply_summary(decision, shop_id, ports, context)
            out.applied.append({"kind": "summary"})
        elif isinstance(decision, RevenueDecision):
            out.revenue_result = await self._apply_revenue(decision, shop_id, ports, context)
            out.applied.append({"kind": "revenue"})
        elif isinstance(decision, RepairRecommendationDecision):
            entry = await self._apply_repair_recommendation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "repair_recommendation"})
        elif isinstance(decision, EstimateExplanationDecision):
            entry = await self._apply_estimate_explanation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "estimate_explanation"})
        elif isinstance(decision, ApprovalRequestDecision):
            entry = await self._apply_approval_request(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "approval_request"})
        elif isinstance(decision, RepairStatusDecision):
            entry = await self._apply_repair_status(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "repair_status"})
        elif isinstance(decision, MaintenanceReminderDecision):
            entry = await self._apply_maintenance_reminder(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "maintenance_reminder"})
        elif isinstance(decision, ReviewRequestDecision):
            entry = await self._apply_review_request(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "review_request"})
        elif isinstance(decision, RetentionDecision):
            entry = await self._apply_retention(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "retention"})
        elif isinstance(decision, CustomerCommunicationDecision):
            entry = await self._apply_customer_communication(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "customer_communication"})
        elif isinstance(decision, InspectionAnalysisDecision):
            entry = await self._apply_inspection_analysis(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "inspection_analysis"})
        elif isinstance(decision, SafetyAlertDecision):
            entry = await self._apply_safety_alert(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.escalations.append(entry)
            out.applied.append({"kind": "safety_alert", "urgent": decision.urgent})
        elif isinstance(decision, CustomerExplanationDecision):
            entry = await self._apply_customer_explanation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "customer_explanation"})
        elif isinstance(decision, FollowUpDecision):
            entry = await self._apply_follow_up(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "follow_up"})
        elif isinstance(decision, PartsAvailabilityDecision):
            entry = await self._apply_parts_availability(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "parts_availability", "sku": decision.sku})
        elif isinstance(decision, InventoryRiskDecision):
            entry = await self._apply_inventory_risk(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "inventory_risk", "risk_level": decision.risk_level})
        elif isinstance(decision, PurchaseRecommendationDecision):
            entry = await self._apply_purchase_recommendation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "purchase_recommendation", "sku": decision.sku})
        elif isinstance(decision, RepairReadinessDecision):
            entry = await self._apply_repair_readiness(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "repair_readiness", "ready": decision.ready})
        elif isinstance(decision, PartCostDecision):
            entry = await self._apply_part_cost(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "part_cost", "sku": decision.sku})
        elif isinstance(decision, CustomerMemoryDecision):
            entry = await self._apply_customer_memory(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "customer_memory", "action": decision.action})
        elif isinstance(decision, VehicleMemoryDecision):
            entry = await self._apply_vehicle_memory(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "vehicle_memory", "action": decision.action})
        elif isinstance(decision, ShopPreferenceDecision):
            entry = await self._apply_shop_preference(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "shop_preference"})
        elif isinstance(decision, KnowledgeRetrievalDecision):
            entry = await self._apply_knowledge_retrieval(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "knowledge_retrieval", "read_only": True})
        elif isinstance(decision, CustomerRetentionDecision):
            entry = await self._apply_customer_retention(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "customer_retention", "priority": decision.priority})
        elif isinstance(decision, RevenueOpportunityDecision):
            entry = await self._apply_revenue_opportunity_decision(
                decision, shop_id, ports, context
            )
            out.advisor_results.append(entry)
            out.applied.append({"kind": "revenue_opportunity"})
        elif isinstance(decision, ServiceRecommendationDecision):
            entry = await self._apply_service_recommendation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "service_recommendation", "service": decision.service})
        elif isinstance(decision, ContactTimingDecision):
            entry = await self._apply_contact_timing(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "contact_timing", "window": decision.preferred_window})
        elif isinstance(decision, CampaignRecommendationDecision):
            entry = await self._apply_campaign_recommendation(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append(
                {"kind": "campaign_recommendation", "auto_send": False, "sent": False}
            )
        elif isinstance(decision, CustomerValueDecision):
            entry = await self._apply_customer_value(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append({"kind": "customer_value"})
        elif isinstance(decision, LearningFeedbackDecision):
            entry = await self._apply_learning_feedback(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append(
                {
                    "kind": "learning_feedback",
                    "requires_review": True,
                    "rules_changed": False,
                }
            )
        elif isinstance(decision, OptimizationDecision):
            entry = await self._apply_optimization(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append(
                {
                    "kind": "optimization",
                    "auto_apply": False,
                    "applied": False,
                    "workflow_modified": False,
                }
            )
        elif isinstance(decision, PatternDiscoveryDecision):
            entry = await self._apply_pattern_discovery(decision, shop_id, ports, context)
            out.advisor_results.append(entry)
            out.applied.append(
                {
                    "kind": "pattern_discovery",
                    "pattern_key": decision.pattern_key,
                    "rules_changed": False,
                }
            )
        else:
            # Intent / Priority — decide-only; still record on Conversation
            await self._record_conversation_decision(decision, shop_id, ports, context)
            out.applied.append({"kind": str(getattr(decision, "kind", "unknown")), "noop": True})

    async def _apply_customer(
        self,
        decision: CustomerDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> CustomerResolveResult:
        from app.plugins.framework.capability import Capability

        if decision.action == "merge" and decision.primary_id and decision.duplicate_ids:
            merged = await self._invoke_cap(
                Capability.MERGE_CUSTOMER.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                primary_id=decision.primary_id,
                duplicate_ids=list(decision.duplicate_ids),
            )
            context.customer_id = merged.id
            await self._emit_event(
                DomainEventType.CRM_UPDATED,
                shop_id,
                {"action": "merge", "customer_id": str(merged.id)},
                context.correlation_id,
            )
            return CustomerResolveResult(
                customer=merged, merged_from=list(decision.duplicate_ids), action="merged"
            )

        if decision.action == "create":
            name = (decision.name or "").strip() or "Unknown Customer"
            profile = CustomerProfile(
                id=uuid4(),
                shop_id=shop_id,
                name=name,
                phone=decision.phone,
                email=decision.email.lower().strip() if decision.email else None,
            )
            created = await self._invoke_cap(
                Capability.CREATE_CUSTOMER.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                profile=profile,
            )
            context.customer_id = created.id
            await self._emit_event(
                DomainEventType.CUSTOMER_CREATED,
                shop_id,
                {"customer_id": str(created.id), "name": created.name},
                context.correlation_id,
            )
            return CustomerResolveResult(customer=created, is_new=True, action="created")

        if decision.action == "update" and decision.primary_id:
            existing = await self._invoke_cap(
                Capability.FIND_CUSTOMER.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                customer_id=decision.primary_id,
            )
            if existing is None:
                raise LookupError("Customer not found for update")
            for key, value in decision.profile_patch.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            updated = await self._invoke_cap(
                Capability.UPDATE_CUSTOMER.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                profile=existing,
            )
            context.customer_id = updated.id
            return CustomerResolveResult(customer=updated, action="updated")

        return CustomerResolveResult(customer=None, action="none")

    async def _apply_vehicle(
        self,
        decision: VehicleDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> VehicleResolveResult:
        from app.plugins.framework.capability import Capability

        if decision.action == "create":
            if not decision.vin or not decision.year or not decision.make or not decision.model:
                raise ValueError("VIN, year, make, and model required to create vehicle")
            vehicle = VehicleRecord(
                id=uuid4(),
                shop_id=shop_id,
                vin=decision.vin.upper(),
                year=decision.year,
                make=decision.make,
                model=decision.model,
                mileage=decision.mileage or 0,
                customer_id=decision.customer_id or context.customer_id,
            )
            vehicle = await self._invoke_cap(
                Capability.CREATE_VEHICLE.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle=vehicle,
            )
            context.vehicle_id = vehicle.id
            await self._emit_event(
                DomainEventType.VEHICLE_CREATED,
                shop_id,
                {"vehicle_id": str(vehicle.id), "vin": vehicle.vin},
                context.correlation_id,
            )
            repairs = await self._invoke_cap(
                Capability.REPAIR_HISTORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle_id=vehicle.id,
            )
            timeline = _maintenance_timeline(vehicle, repairs)
            return VehicleResolveResult(
                vehicle=vehicle,
                repair_history=repairs,
                maintenance_timeline=timeline,
                action="created",
            )

        if decision.action == "update_mileage" and decision.vehicle_id is not None:
            vehicle = await self._invoke_cap(
                Capability.FIND_VEHICLE.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle_id=decision.vehicle_id,
            )
            if vehicle is None:
                raise LookupError("Vehicle not found")
            mileage = decision.mileage if decision.mileage is not None else vehicle.mileage
            updated = VehicleRecord(
                id=vehicle.id,
                shop_id=vehicle.shop_id,
                vin=vehicle.vin,
                year=vehicle.year,
                make=vehicle.make,
                model=vehicle.model,
                mileage=mileage,
                customer_id=vehicle.customer_id,
                license_plate=vehicle.license_plate,
            )
            updated = await self._invoke_cap(
                Capability.UPDATE_VEHICLE.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle=updated,
            )
            context.vehicle_id = updated.id
            repairs = await self._invoke_cap(
                Capability.REPAIR_HISTORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle_id=updated.id,
            )
            return VehicleResolveResult(
                vehicle=updated,
                repair_history=repairs,
                maintenance_timeline=_maintenance_timeline(updated, repairs),
                action="mileage_updated",
            )

        return VehicleResolveResult(vehicle=None, action="none")

    async def _apply_appointment(
        self,
        decision: AppointmentDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> SchedulingResult:
        from app.plugins.framework.capability import Capability

        if decision.action == "list_slots":
            if decision.offer_policy == "ask_time":
                pending_action = decision.hold_action or "book"
                if pending_action not in {"book", "reschedule"}:
                    pending_action = "book"
                return SchedulingResult(
                    action="list_slots",
                    success=True,
                    available_slots=[],
                    message="ask_preferred_time",
                    metadata={
                        "ask_preferred_time": True,
                        "action": pending_action,
                    },
                    decision=decision,
                )
            if decision.offer_policy == "unavailable":
                preferred_iso = (
                    decision.preferred_start.isoformat()
                    if decision.preferred_start is not None
                    else None
                )
                # Classify date-vs-time so counselor re-asks only the broken half.
                from app.agents.scheduling.service import SchedulingAgent

                aspect_slots = await self._invoke_cap(
                    Capability.FIND_AVAILABLE_SLOT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    days_ahead=decision.days_ahead,
                    duration_minutes=decision.duration_minutes,
                    repair_type=decision.required_skill,
                )
                aspect = SchedulingAgent.classify_unavailable_aspect(
                    list(aspect_slots or []),
                    decision.preferred_start,
                )
                pending_action = decision.hold_action or "book"
                if pending_action not in {"book", "reschedule"}:
                    pending_action = "book"
                meta: dict = {
                    "preferred_time_unavailable": True,
                    "unavailable_aspect": aspect,
                    "action": pending_action,
                    "preferred_start": preferred_iso,
                }
                # Preferred calendar day has zero openings → date (closed/full).
                if decision.preferred_start is not None and not (
                    SchedulingAgent._same_day_openings(
                        list(aspect_slots or []), decision.preferred_start
                    )
                ):
                    meta["unavailable_aspect"] = "date"
                    meta["closed_day"] = True
                return SchedulingResult(
                    action="list_slots",
                    success=False,
                    available_slots=[],
                    message="preferred_time_unavailable",
                    metadata=meta,
                    decision=decision,
                )
            slots = await self._invoke_cap(
                Capability.FIND_AVAILABLE_SLOT.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                days_ahead=decision.days_ahead,
                duration_minutes=decision.duration_minutes,
                repair_type=decision.required_skill,
            )
            # Soft day / part-of-day prefs must survive WF re-fetch (agent already
            # narrowed openings; capability returns week-ranked candidates).
            if (
                decision.preferred_start is not None
                and decision.recommended_slot_start is None
            ):
                slots = self._filter_slots_for_soft_preference(
                    slots,
                    preferred_start=decision.preferred_start,
                    preferred_end=decision.preferred_end,
                )
            meta: dict = {}
            message = f"{len(slots)} slots available"
            # Preserve counselor confirmation candidate chosen by SchedulingAgent.
            if decision.recommended_slot_start is not None:
                start = decision.recommended_slot_start
                end = decision.recommended_slot_end or start
                pending_action = decision.hold_action or "book"
                if pending_action not in {"book", "reschedule"}:
                    pending_action = "book"
                meta = {
                    "awaiting_confirmation": True,
                    "action": pending_action,
                    "pending_slot_start": start.isoformat(),
                    "pending_slot_end": end.isoformat(),
                }
                message = (
                    "awaiting_reschedule_confirmation"
                    if pending_action == "reschedule"
                    else "awaiting_booking_confirmation"
                )
            return SchedulingResult(
                action="list_slots",
                success=True,
                available_slots=slots,
                message=message,
                metadata=meta,
                decision=decision,
            )

        if decision.action == "book":
            duration = decision.duration_minutes
            start = decision.recommended_slot_start
            end = decision.recommended_slot_end
            if start is None or end is None:
                # Require a concrete preferred time — never invent slots[0],
                # and never silently book a later opening after preferred.
                if decision.preferred_start is None:
                    return SchedulingResult(
                        action="book",
                        success=False,
                        message="Preferred start required to book",
                    )
                slots = await self._invoke_cap(
                    Capability.FIND_AVAILABLE_SLOT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    days_ahead=decision.days_ahead,
                    duration_minutes=duration,
                    repair_type=decision.required_skill,
                )
                if not slots:
                    return SchedulingResult(action="book", success=False, message="No available slots")
                # Exact preferred minute only (shop-local, ignore sub-minute noise).
                from app.agents.scheduling.service import SchedulingAgent

                slot = SchedulingAgent._find_exact_slot(slots, decision.preferred_start)
                if slot is None:
                    aspect = SchedulingAgent.classify_unavailable_aspect(
                        slots, decision.preferred_start
                    )
                    return SchedulingResult(
                        action="list_slots",
                        success=False,
                        available_slots=[],
                        message="preferred_time_unavailable",
                        metadata={
                            "preferred_time_unavailable": True,
                            "unavailable_aspect": aspect,
                            "action": "book",
                            "preferred_start": decision.preferred_start.isoformat(),
                        },
                        decision=decision,
                    )
                start, end = slot.start, slot.end
            if duration and start is not None:
                end = start + timedelta(minutes=int(duration))
            preferred_iso = start.isoformat() if start is not None else (
                decision.preferred_start.isoformat()
                if decision.preferred_start is not None
                else None
            )

            def _unavailable(message: str, *, errors: list[str] | None = None) -> SchedulingResult:
                # Map capacity/hours failures to counselor's preferred_time_unavailable.
                from app.agents.scheduling.service import SchedulingAgent

                aspect = SchedulingAgent.classify_unavailable_aspect(
                    [],  # validation failed for this exact window; treat as time-level
                    start if start is not None else decision.preferred_start,
                )
                # Capacity/hour rejection is almost always the clock (day had a candidate).
                if aspect == "both" and (
                    start is not None or decision.preferred_start is not None
                ):
                    aspect = "time"
                return SchedulingResult(
                    action="list_slots",
                    success=False,
                    available_slots=[],
                    message="preferred_time_unavailable",
                    metadata={
                        "preferred_time_unavailable": True,
                        "unavailable_aspect": aspect,
                        "action": "book",
                        "preferred_start": preferred_iso,
                        "errors": list(errors or [message]),
                    },
                    decision=decision,
                )

            # Workflow validates availability before creating the appointment
            validation = await self._invoke_cap(
                Capability.VALIDATE_APPOINTMENT.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                start=start,
                end=end,
            )
            if isinstance(validation, dict) and not validation.get("valid", True):
                errs = list(validation.get("errors") or ["conflict"])
                return _unavailable(
                    "Slot not available: " + "; ".join(errs),
                    errors=errs,
                )
            notes = decision.reason
            if decision.service_name:
                svc_note = f"service:{decision.service_name}"
                notes = f"{notes}; {svc_note}" if notes else svc_note
            try:
                appt = await self._invoke_cap(
                    Capability.BOOK_APPOINTMENT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    start=start,
                    end=end,
                    customer_id=decision.customer_id or context.customer_id,
                    vehicle_id=decision.vehicle_id or context.vehicle_id,
                    notes=notes,
                    service_id=decision.service_id,
                    service_name=decision.service_name,
                    duration_minutes=duration,
                    repair_type=decision.required_skill,
                    required_bay=decision.required_bay,
                )
            except Exception as exc:  # noqa: BLE001 — surface capacity race as unavailable
                return _unavailable(str(exc) or "Unable to book requested slot")
            from app.plugins.scheduling.plugin import reminders_for

            reminders = reminders_for(appt)
            await self._emit_event(
                DomainEventType.APPOINTMENT_BOOKED,
                shop_id,
                {
                    "appointment_id": str(appt.id),
                    "customer_id": str(appt.customer_id) if appt.customer_id else None,
                    "start": appt.start.isoformat(),
                    "end": appt.end.isoformat(),
                    "service_id": str(decision.service_id) if decision.service_id else None,
                    "service_name": decision.service_name,
                    "duration_minutes": duration,
                },
                context.correlation_id,
            )
            return SchedulingResult(
                action="book",
                success=True,
                appointment=appt,
                reminders=reminders,
                message="Appointment booked",
                metadata={
                    "service_id": str(decision.service_id) if decision.service_id else None,
                    "service_name": decision.service_name,
                    "duration_minutes": duration,
                },
            )

        if decision.action == "reschedule":
            from app.agents.scheduling.service import SchedulingAgent

            if not decision.appointment_id:
                slots = await self._invoke_cap(
                    Capability.FIND_AVAILABLE_SLOT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    repair_type=decision.required_skill,
                )
                return SchedulingResult(
                    action="reschedule",
                    success=False,
                    available_slots=slots,
                    message="appointment_id required to reschedule; slots provided",
                )
            start = decision.recommended_slot_start
            end = decision.recommended_slot_end
            if start is None or end is None:
                # Never invent slots[0]. Prefer exact preferred_start only.
                preferred = decision.preferred_start
                if preferred is None:
                    return SchedulingResult(
                        action="list_slots",
                        success=False,
                        available_slots=[],
                        message="preferred_time_unavailable",
                        metadata={
                            "preferred_time_unavailable": True,
                            "unavailable_aspect": "both",
                            "action": "reschedule",
                        },
                        decision=decision,
                    )
                slots = await self._invoke_cap(
                    Capability.FIND_AVAILABLE_SLOT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    repair_type=decision.required_skill,
                    duration_minutes=decision.duration_minutes,
                )
                slot = SchedulingAgent._find_exact_slot(list(slots or []), preferred)
                if slot is None:
                    aspect = SchedulingAgent.classify_unavailable_aspect(
                        list(slots or []), preferred
                    )
                    return SchedulingResult(
                        action="list_slots",
                        success=False,
                        available_slots=[],
                        message="preferred_time_unavailable",
                        metadata={
                            "preferred_time_unavailable": True,
                            "unavailable_aspect": aspect,
                            "action": "reschedule",
                            "preferred_start": preferred.isoformat(),
                        },
                        decision=decision,
                    )
                start, end = slot.start, slot.end
            duration = decision.duration_minutes
            if duration and end is not None and start is not None:
                end = start + timedelta(minutes=int(duration))

            preferred_iso = start.isoformat() if start is not None else (
                decision.preferred_start.isoformat()
                if decision.preferred_start is not None
                else None
            )

            def _reschedule_unavailable(
                message: str, *, errors: list[str] | None = None
            ) -> SchedulingResult:
                aspect = SchedulingAgent.classify_unavailable_aspect(
                    [],
                    start if start is not None else decision.preferred_start,
                )
                if aspect == "both" and (
                    start is not None or decision.preferred_start is not None
                ):
                    aspect = "time"
                return SchedulingResult(
                    action="list_slots",
                    success=False,
                    available_slots=[],
                    message="preferred_time_unavailable",
                    metadata={
                        "preferred_time_unavailable": True,
                        "unavailable_aspect": aspect,
                        "action": "reschedule",
                        "preferred_start": preferred_iso,
                        "errors": list(errors or [message]),
                    },
                    decision=decision,
                )

            validation = await self._invoke_cap(
                Capability.VALIDATE_APPOINTMENT.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                start=start,
                end=end,
                exclude_id=decision.appointment_id,
            )
            if isinstance(validation, dict) and not validation.get("valid", True):
                errs = list(validation.get("errors") or ["conflict"])
                return _reschedule_unavailable(
                    "Slot not available: " + "; ".join(errs),
                    errors=errs,
                )
            try:
                appt = await self._invoke_cap(
                    Capability.RESCHEDULE_APPOINTMENT.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    appointment_id=decision.appointment_id,
                    start=start,
                    end=end,
                    service_id=decision.service_id,
                    service_name=decision.service_name,
                    duration_minutes=duration,
                    repair_type=decision.required_skill,
                    required_bay=decision.required_bay,
                )
            except Exception as exc:  # noqa: BLE001 — capacity / hours rejection
                return _reschedule_unavailable(str(exc) or "Unable to reschedule")
            from app.plugins.scheduling.plugin import reminders_for

            return SchedulingResult(
                action="reschedule",
                success=True,
                appointment=appt,
                reminders=reminders_for(appt),
                message="Appointment rescheduled",
                metadata={
                    "service_id": str(decision.service_id) if decision.service_id else None,
                    "service_name": decision.service_name,
                    "duration_minutes": duration,
                },
            )

        if decision.action == "cancel":
            if not decision.appointment_id:
                return SchedulingResult(action="cancel", success=False, message="appointment_id required")
            appt = await self._invoke_cap(
                Capability.CANCEL_APPOINTMENT.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                appointment_id=decision.appointment_id,
                reason=decision.reason,
            )
            await self._emit_event(
                DomainEventType.APPOINTMENT_CANCELLED,
                shop_id,
                {"appointment_id": str(appt.id), "reason": decision.reason},
                context.correlation_id,
            )
            return SchedulingResult(
                action="cancel", success=True, appointment=appt, message="Appointment cancelled"
            )

        return SchedulingResult(action="noop", success=True, message="No scheduling action required")

    async def _apply_crm(
        self,
        decision: CrmUpdateDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> CrmUpdateResult:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id is None:
            return CrmUpdateResult(
                customer_id=None,
                customer_summary="No customer linked; CRM update skipped.",
            )

        entries: list[TimelineEntry] = []
        communication_recorded = False
        repair_updated = False

        if decision.message and decision.channel:
            entries.append(
                await self._invoke_cap(
                    Capability.ADD_COMMUNICATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    channel=decision.channel,
                    message=decision.message,
                )
            )
            communication_recorded = True
        if decision.repair_note:
            entries.append(
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="repair",
                    summary=decision.repair_note,
                )
            )
            # Prefer dedicated repair-note path when available via communications port
            # through capability ADD_TIMELINE keeps Workflow free of CRM imports.
            repair_updated = True
        if decision.intent:
            entries.append(
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="intent",
                    summary=f"Detected intent: {decision.intent}",
                )
            )

        timeline = await self._invoke_cap(
            Capability.CUSTOMER_TIMELINE.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            customer_id=customer_id,
        )
        summary = _crm_summary(customer_id, timeline, decision.intent)
        await self._emit_event(
            DomainEventType.CRM_UPDATED,
            shop_id,
            {"customer_id": str(customer_id), "entries": len(entries)},
            context.correlation_id,
        )
        return CrmUpdateResult(
            customer_id=customer_id,
            communication_recorded=communication_recorded,
            repair_updated=repair_updated,
            timeline_entries=timeline,
            customer_summary=summary,
        )

    async def _apply_marketing(
        self, decision: MarketingDecision, ports: DecisionPorts
    ) -> MarketingActionResult:
        dispatcher = ports.marketing_dispatcher
        if dispatcher is None:
            raise RuntimeError("marketing_dispatcher port required")
        action = MarketingActionResult(
            action_type=decision.action_type,
            channel=decision.channel,
            customer_id=decision.customer_id,
            template=decision.template,
            body=decision.body,
            scheduled_at=decision.scheduled_at or datetime.now(timezone.utc),
            dispatched=False,
            payload=dict(decision.context),
        )
        return await dispatcher.dispatch(action)

    async def _apply_escalation(
        self,
        decision: EscalationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        entry = {
            "shop_id": str(shop_id),
            "reason": decision.reason,
            "priority": decision.priority,
            "details": decision.details,
            "correlation_id": context.correlation_id,
            "conversation_id": context.conversation_id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if decision.escalate and self._escalate:
            self._escalate(
                shop_id=shop_id,
                reason=decision.reason or "AI recommended escalation",
                details=decision.details,
            )
        cid = self._conversation_uuid(context)
        if cid is not None:
            try:
                from app.plugins.framework.capability import Capability

                await self._invoke_cap(
                    Capability.UPDATE_CONVERSATION.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    conversation_id=cid,
                    status="escalated" if decision.escalate else None,
                    priority=decision.priority,
                    decision={
                        "kind": "escalation",
                        "escalate": decision.escalate,
                        "reason": decision.reason,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.debug("conversation.escalation_update_skipped", exc_info=True)
        return entry

    async def _apply_memory(
        self,
        decision: MemoryDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> None:
        """Persist MemoryDecision via Memory Plugin SaveMemory (not AI-direct write)."""
        from app.plugins.framework.capability import Capability

        if not decision.facts:
            return
        for fact in decision.facts:
            content = str(fact.get("content") or fact.get("text") or "").strip()
            if not content:
                continue
            try:
                await self._invoke_cap(
                    Capability.SAVE_MEMORY.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    content=content,
                    summary=fact.get("summary") or decision.rationale,
                    memory_type=fact.get("memory_type"),
                    category=fact.get("category"),
                    customer_id=fact.get("customer_id") or context.customer_id,
                    vehicle_id=fact.get("vehicle_id") or context.vehicle_id,
                    importance=fact.get("importance", 0.6),
                    tags=list(fact.get("tags") or ["memory_decision"]),
                    metadata=dict(fact.get("metadata") or {}),
                    source="workflow",
                )
            except Exception:  # noqa: BLE001
                # Fallback to legacy write_facts if Memory Plugin not loaded
                memory = ports.memory_service
                if memory is not None and hasattr(memory, "write_facts"):
                    memory.write_facts(shop_id, [fact])
                else:
                    logger.debug("memory.save_skipped", exc_info=True)

    async def _apply_customer_memory(
        self,
        decision: CustomerMemoryDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if decision.action == "noop" or customer_id is None:
            return {"ok": False, "reason": "noop_or_missing_customer"}
        if decision.action == "update_profile":
            result = await self._invoke_cap(
                Capability.UPDATE_CUSTOMER_PROFILE.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                customer_id=customer_id,
                patch={
                    **decision.patch,
                    "summary": decision.content or decision.patch.get("summary"),
                    "rationale": decision.rationale,
                    "importance": decision.importance,
                    "tags": list(decision.tags),
                },
            )
        else:
            result = await self._invoke_cap(
                Capability.SAVE_MEMORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                content=decision.content or str(decision.patch),
                category=decision.category,
                memory_type="customer",
                customer_id=customer_id,
                importance=decision.importance,
                tags=list(decision.tags) or ["customer_memory"],
                summary=decision.rationale,
                source="workflow",
            )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "result": result}

    async def _apply_vehicle_memory(
        self,
        decision: VehicleMemoryDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        vehicle_id = decision.vehicle_id or context.vehicle_id
        if decision.action == "noop" or vehicle_id is None:
            return {"ok": False, "reason": "noop_or_missing_vehicle"}
        if decision.action == "update_health":
            health = {
                **decision.health,
                "summary": decision.content or decision.health.get("summary"),
                "rationale": decision.rationale,
                "importance": decision.importance,
                "customer_id": str(decision.customer_id or context.customer_id or "") or None,
            }
            result = await self._invoke_cap(
                Capability.UPDATE_VEHICLE_HEALTH.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                vehicle_id=vehicle_id,
                health=health,
            )
        else:
            result = await self._invoke_cap(
                Capability.SAVE_MEMORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                content=decision.content or "Vehicle history note",
                category="vehicle_history",
                memory_type="vehicle",
                vehicle_id=vehicle_id,
                customer_id=decision.customer_id or context.customer_id,
                importance=decision.importance,
                tags=list(decision.tags) or ["vehicle_memory"],
                summary=decision.rationale,
                source="workflow",
            )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "result": result}

    async def _apply_shop_preference(
        self,
        decision: ShopPreferenceDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        saved: list[Any] = []
        for key, value in (decision.preferences or {}).items():
            saved.append(
                await self._invoke_cap(
                    Capability.SAVE_MEMORY.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    content=f"Shop preference {key}={value}",
                    category="shop_preferences",
                    memory_type="shop",
                    importance=0.75,
                    tags=["shop_preference", str(key)],
                    metadata={"key": key, "value": value},
                    summary=decision.rationale,
                    source="workflow",
                )
            )
        # Also update structured shop profile preferences via manager when available
        memory = ports.memory_service
        manager = getattr(memory, "manager", None) if memory is not None else None
        if manager is None:
            try:
                from app.memory.factory import get_memory_runtime

                manager = get_memory_runtime().manager
            except Exception:  # noqa: BLE001
                manager = None
        if manager is not None and decision.preferences:
            await manager.apply_shop_preference_decision(
                shop_id, preferences=decision.preferences, rationale=decision.rationale
            )
        if manager is not None and decision.profile_patch:
            await manager.shop_profile.update(shop_id, decision.profile_patch)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "saved": len(saved)}

    async def _apply_knowledge_retrieval(
        self,
        decision: KnowledgeRetrievalDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Read-only — populate context metadata; never writes memory."""
        from app.plugins.framework.capability import Capability

        result = await self._invoke_cap(
            Capability.RETRIEVE_KNOWLEDGE.value,
            shop_id=shop_id,
            ports=ports,
            context=context,
            query=decision.query,
            limit=decision.limit,
        )
        docs = (result or {}).get("documents") if isinstance(result, dict) else result
        context.metadata["retrieved_knowledge"] = docs
        context.metadata["knowledge_query"] = decision.query
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "documents": docs, "read_only": True}

    async def _apply_customer_retention(
        self,
        decision: CustomerRetentionDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Record retention plan — never contact customer or apply discounts."""
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="retention",
                    summary=decision.plan or decision.rationale,
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.retention_timeline_skipped", exc_info=True)
            try:
                await self._invoke_cap(
                    Capability.SAVE_MEMORY.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    content=decision.plan or "Retention plan",
                    category="customer_history",
                    memory_type="customer",
                    customer_id=customer_id,
                    tags=["retention", decision.priority],
                    metadata={
                        "risk_score": decision.risk_score,
                        "actions": list(decision.actions),
                        "suggested_offer_ignored": decision.suggested_offer,
                    },
                    source="workflow",
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.retention_memory_skipped", exc_info=True)
        try:
            from app.revenue.factory import get_revenue_intelligence_runtime

            await get_revenue_intelligence_runtime().engine.insights.record(
                shop_id,
                kind="retention_plan",
                customer_id=customer_id,
                payload={
                    "plan": decision.plan,
                    "risk_score": decision.risk_score,
                    "actions": list(decision.actions),
                    "priority": decision.priority,
                },
            )
        except Exception:  # noqa: BLE001
            pass
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ok": True,
            "contacted": False,
            "discount_applied": False,
            "plan": decision.plan,
        }

    async def _apply_revenue_opportunity_decision(
        self,
        decision: RevenueOpportunityDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="revenue_opportunity",
                    summary=decision.title or decision.rationale,
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.opportunity_timeline_skipped", exc_info=True)
        await self._emit_event(
            DomainEventType.REVENUE_UPDATED,
            shop_id,
            {
                "kind": decision.opportunity_kind,
                "title": decision.title,
                "expected_revenue": decision.expected_revenue,
                "customer_id": str(customer_id) if customer_id else None,
            },
            context.correlation_id,
        )
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "priced": False, "title": decision.title}

    async def _apply_service_recommendation(
        self,
        decision: ServiceRecommendationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="service_recommendation",
                    summary=f"{decision.service}: {decision.reason or decision.rationale}",
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.service_rec_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "booked": False, "service": decision.service}

    async def _apply_contact_timing(
        self,
        decision: ContactTimingDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.SAVE_MEMORY.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    content=f"Preferred contact: {decision.channel} @ {decision.preferred_window}",
                    category="customer_preferences",
                    memory_type="customer",
                    customer_id=customer_id,
                    tags=["contact_timing", decision.channel],
                    metadata={
                        "channel": decision.channel,
                        "preferred_window": decision.preferred_window,
                    },
                    source="workflow",
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.contact_timing_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "sent": False, "window": decision.preferred_window}

    async def _apply_campaign_recommendation(
        self,
        decision: CampaignRecommendationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Store campaign suggestion only — never dispatch marketing (auto_send ignored)."""
        _ = ports
        try:
            from app.revenue.factory import get_revenue_intelligence_runtime

            await get_revenue_intelligence_runtime().engine.insights.record(
                shop_id,
                kind="campaign_suggestion",
                customer_id=decision.customer_id or context.customer_id,
                payload={
                    "campaign_type": decision.campaign_type,
                    "channel": decision.channel,
                    "message_draft": decision.message_draft,
                    "audience_size": decision.audience_size,
                    "auto_send": False,
                    "ai_requested_auto_send": bool(decision.auto_send),
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("revenue.campaign_suggestion_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ok": True,
            "sent": False,
            "discount_applied": False,
            "auto_send": False,
            "campaign_type": decision.campaign_type,
        }

    async def _apply_customer_value(
        self,
        decision: CustomerValueDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        from app.plugins.framework.capability import Capability

        customer_id = decision.customer_id or context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.SAVE_MEMORY.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    content=(
                        f"CLV={decision.lifetime_value} "
                        f"health={decision.health_score} risk={decision.churn_risk}"
                    ),
                    category="customer_history",
                    memory_type="customer",
                    customer_id=customer_id,
                    tags=["customer_value", "clv"],
                    metadata={
                        "lifetime_value": decision.lifetime_value,
                        "health_score": decision.health_score,
                        "churn_risk": decision.churn_risk,
                    },
                    source="workflow",
                )
            except Exception:  # noqa: BLE001
                logger.debug("revenue.customer_value_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {"ok": True, "lifetime_value": decision.lifetime_value}

    async def _apply_learning_feedback(
        self,
        decision: LearningFeedbackDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Record learning feedback for review — never changes business rules."""
        from app.plugins.framework.capability import Capability

        _ = ports
        customer_id = context.customer_id
        if customer_id:
            try:
                await self._invoke_cap(
                    Capability.ADD_TIMELINE.value,
                    shop_id=shop_id,
                    ports=ports,
                    context=context,
                    customer_id=customer_id,
                    kind="learning_feedback",
                    summary=decision.summary or decision.rationale,
                )
            except Exception:  # noqa: BLE001
                logger.debug("learning.feedback_timeline_skipped", exc_info=True)
        try:
            await self._invoke_cap(
                Capability.SAVE_MEMORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                content=decision.summary or "Learning feedback",
                category="general",
                memory_type="semantic",
                customer_id=customer_id,
                tags=["learning", decision.source, "review_required"],
                metadata={
                    "source": decision.source,
                    "insights": list(decision.insights),
                    "metrics": dict(decision.metrics),
                    "requires_review": True,
                    "rules_changed": False,
                },
                source="workflow",
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.feedback_memory_skipped", exc_info=True)
        try:
            from app.learning.factory import get_learning_runtime

            await get_learning_runtime().engine.collector.collect_decision_result(
                shop_id,
                decision_kind="learning_feedback",
                outcome_kind="staff_feedback"
                if decision.source == "staff"
                else "conversation",
                success=True,
                customer_id=customer_id,
                notes=decision.summary,
                metadata={"source": decision.source, "insights": list(decision.insights)},
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.feedback_collect_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ok": True,
            "requires_review": True,
            "rules_changed": False,
            "workflow_modified": False,
            "prices_changed": False,
            "permissions_changed": False,
        }

    async def _apply_optimization(
        self,
        decision: OptimizationDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Store optimization proposal only — auto_apply is always ignored."""
        from app.plugins.framework.capability import Capability
        from uuid import uuid4

        _ = ports
        try:
            from app.learning.factory import get_learning_runtime
            from app.learning.models.decision_result import LearningFeedback

            await get_learning_runtime().store.save_feedback(
                LearningFeedback(
                    id=uuid4(),
                    shop_id=shop_id,
                    source="system",
                    comment=decision.rationale or "; ".join(decision.suggestions),
                    decision_kind=decision.target,
                    metadata={
                        "kind": "optimization",
                        "suggestions": list(decision.suggestions),
                        "expected_impact": decision.expected_impact,
                        "auto_apply": False,
                        "ai_requested_auto_apply": bool(decision.auto_apply),
                        "requires_review": True,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.optimization_store_skipped", exc_info=True)
        try:
            await self._invoke_cap(
                Capability.SAVE_MEMORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                content=(
                    f"Optimization for {decision.target}: "
                    + "; ".join(decision.suggestions[:5])
                ),
                category="general",
                memory_type="semantic",
                tags=["learning", "optimization", "review_required"],
                metadata={
                    "target": decision.target,
                    "suggestions": list(decision.suggestions),
                    "auto_apply": False,
                },
                source="workflow",
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.optimization_memory_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ok": True,
            "applied": False,
            "auto_apply": False,
            "workflow_modified": False,
            "prices_changed": False,
            "permissions_changed": False,
            "suggestions": list(decision.suggestions),
        }

    async def _apply_pattern_discovery(
        self,
        decision: PatternDiscoveryDecision,
        shop_id: UUID,
        ports: DecisionPorts,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Record discovered pattern — never promotes to live business rules."""
        from app.plugins.framework.capability import Capability
        from uuid import uuid4

        _ = ports
        try:
            from app.learning.factory import get_learning_runtime
            from app.learning.models.decision_result import SuccessPattern

            await get_learning_runtime().store.save_pattern(
                SuccessPattern(
                    id=uuid4(),
                    shop_id=shop_id,
                    pattern_key=decision.pattern_key or "unknown",
                    description=decision.description or decision.rationale,
                    support_count=decision.support_count,
                    success_rate=decision.success_rate,
                    confidence=decision.confidence,
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.pattern_store_skipped", exc_info=True)
        try:
            await self._invoke_cap(
                Capability.SAVE_MEMORY.value,
                shop_id=shop_id,
                ports=ports,
                context=context,
                content=decision.description or f"Pattern {decision.pattern_key}",
                category="general",
                memory_type="semantic",
                tags=["learning", "pattern", decision.pattern_key],
                metadata={
                    "pattern_key": decision.pattern_key,
                    "support_count": decision.support_count,
                    "success_rate": decision.success_rate,
                    "rules_changed": False,
                },
                source="workflow",
            )
        except Exception:  # noqa: BLE001
            logger.debug("learning.pattern_memory_skipped", exc_info=True)
        await self._record_conversation_decision(decision, shop_id, ports, context)
        return {
            "ok": True,
            "pattern_key": decision.pattern_key,
            "rules_changed": False,
            "workflow_modified": False,
        }

    async def _emit_event(
        self,
        event_type: DomainEventType,
        shop_id: UUID,
        payload: dict[str, Any],
        correlation_id: str,
    ) -> None:
        if self._emit is None:
            return
        await self._emit(
            shop_id=shop_id,
            event_type=event_type,
            payload=payload,
            source="workflow.decision_executor",
            correlation_id=correlation_id,
        )


def _reminders_for(appointment: AppointmentRecord) -> list[Reminder]:
    from datetime import timedelta

    return [
        Reminder(
            appointment_id=appointment.id,
            channel="sms",
            send_at=appointment.start - timedelta(hours=24),
            message="Reminder: your appointment is tomorrow.",
        ),
        Reminder(
            appointment_id=appointment.id,
            channel="sms",
            send_at=appointment.start - timedelta(hours=2),
            message="Reminder: your appointment is in 2 hours.",
        ),
    ]


def _crm_summary(
    customer_id: UUID, timeline: list[TimelineEntry], intent: str | None
) -> str:
    parts = [f"Customer {customer_id}: {len(timeline)} timeline events."]
    if intent:
        parts.append(f"Latest intent: {intent}.")
    if timeline:
        last = timeline[-1]
        parts.append(f"Last activity ({last.kind}): {last.summary}")
    return " ".join(parts)


def _maintenance_timeline(vehicle: VehicleRecord, repairs: list[Any]) -> list[Any]:
    from app.agents.vehicle.models import MaintenanceItem

    intervals = [
        ("oil_change", 5000),
        ("tire_rotation", 7500),
        ("cabin_filter", 15000),
        ("brake_inspection", 20000),
        ("transmission_service", 60000),
    ]
    performed = {
        getattr(r, "service_type", "").lower().replace(" ", "_") for r in repairs
    }
    items: list[Any] = []
    now = datetime.now(timezone.utc)
    for service, interval in intervals:
        due = ((vehicle.mileage // interval) + 1) * interval
        status = (
            "completed"
            if service in performed
            else "due_soon"
            if due - vehicle.mileage <= 1000
            else "scheduled"
        )
        items.append(
            MaintenanceItem(
                service=service,
                due_mileage=due,
                due_date=now,
                status=status,
                notes=f"Every {interval} miles",
            )
        )
    return items
