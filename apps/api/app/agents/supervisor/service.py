"""Supervisor Agent service."""

from __future__ import annotations

from typing import Any

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.config import agent_settings
from app.agents.supervisor.models import (
    AgentStageOutput,
    SupervisorDecision,
    SupervisorReviewRequest,
)


class SupervisorAgent(Agent[SupervisorReviewRequest, SupervisorDecision]):
    name = "supervisor"

    async def handle(
        self, payload: SupervisorReviewRequest, context: AgentContext
    ) -> AgentResult[SupervisorDecision]:
        return await self.review(payload, context)

    async def review(
        self, request: SupervisorReviewRequest, context: AgentContext
    ) -> AgentResult[SupervisorDecision]:
        errors = [s.error for s in request.stages if s.error]
        conflicts = self._detect_conflicts(request.stages)
        escalate = False
        reasons: list[str] = []

        for stage in request.stages:
            if stage.escalate:
                escalate = True
                if stage.escalation_reason:
                    reasons.append(f"{stage.agent}: {stage.escalation_reason}")

        if errors:
            escalate = True
            reasons.extend(errors)

        if conflicts:
            escalate = True
            reasons.extend(conflicts)

        if request.is_emergency and agent_settings.escalate_on_emergency:
            escalate = True
            reasons.append("Emergency intent detected")

        if request.is_complaint and agent_settings.escalate_on_complaint:
            escalate = True
            reasons.append("Complaint intent detected")

        status = "escalated" if escalate else ("degraded" if errors else "ok")
        owner_summary = self.generate_owner_summary(request, status, reasons)
        action_items = self._action_items(request, escalate, reasons)

        decision = SupervisorDecision(
            status=status,
            escalate=escalate,
            escalation_reason="; ".join(reasons) if reasons else None,
            conflicts=conflicts,
            errors=list(errors),
            owner_summary=owner_summary,
            action_items=action_items,
            agent_outputs={s.agent: _summarize_data(s) for s in request.stages},
        )
        return AgentResult.ok(decision, escalate=escalate)

    def generate_owner_summary(
        self,
        request: SupervisorReviewRequest,
        status: str,
        reasons: list[str],
    ) -> str:
        successful = [s.agent for s in request.stages if s.success]
        failed = [s.agent for s in request.stages if not s.success]
        parts = [
            f"Pipeline status: {status}.",
            f"Completed agents: {', '.join(successful) or 'none'}.",
        ]
        if request.intent:
            parts.append(f"Customer intent: {request.intent}.")
        if failed:
            parts.append(f"Failed agents: {', '.join(failed)}.")
        if reasons:
            parts.append(f"Attention: {'; '.join(reasons)}.")
        return " ".join(parts)

    def _detect_conflicts(self, stages: list[AgentStageOutput]) -> list[str]:
        conflicts: list[str] = []
        by_name = {s.agent: s for s in stages}

        customer = by_name.get("customer")
        scheduling = by_name.get("scheduling")
        if (
            customer
            and customer.success
            and scheduling
            and scheduling.success
            and isinstance(scheduling.data, dict)
            and scheduling.data.get("action") == "book"
            and scheduling.data.get("success") is True
        ):
            cust_data = customer.data
            if isinstance(cust_data, dict) and cust_data.get("customer") is None:
                conflicts.append("Booked appointment without resolved customer")

        intent = by_name.get("intent")
        if intent and intent.success and scheduling and scheduling.success:
            intent_val = None
            if hasattr(intent.data, "intent"):
                intent_val = getattr(intent.data.intent, "value", intent.data.intent)
            elif isinstance(intent.data, dict):
                intent_val = intent.data.get("intent")
            sched_action = None
            if hasattr(scheduling.data, "action"):
                sched_action = scheduling.data.action
            elif isinstance(scheduling.data, dict):
                sched_action = scheduling.data.get("action")
            if intent_val == "cancel_appointment" and sched_action == "book":
                conflicts.append("Intent was cancel but scheduling booked an appointment")

        return conflicts

    def _action_items(
        self, request: SupervisorReviewRequest, escalate: bool, reasons: list[str]
    ) -> list[str]:
        items: list[str] = []
        if escalate:
            items.append("Human takeover required")
            items.extend(f"Resolve: {r}" for r in reasons[:5])
        if request.is_emergency:
            items.append("Contact customer immediately regarding emergency")
        if request.is_complaint:
            items.append("Owner/manager follow-up on complaint")
        return items


def _summarize_data(stage: AgentStageOutput) -> Any:
    if stage.data is None:
        return {"success": stage.success, "error": stage.error}
    if hasattr(stage.data, "to_json"):
        return stage.data.to_json()
    if hasattr(stage.data, "__dict__"):
        return {"type": type(stage.data).__name__, "success": stage.success}
    return {"success": stage.success}
