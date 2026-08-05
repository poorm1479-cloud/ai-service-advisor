"""Supervisor agent port."""

from __future__ import annotations

from typing import Protocol

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.supervisor.models import SupervisorDecision, SupervisorReviewRequest


class SupervisorAgentPort(Protocol):
    async def review(
        self, request: SupervisorReviewRequest, context: AgentContext
    ) -> AgentResult[SupervisorDecision]: ...
