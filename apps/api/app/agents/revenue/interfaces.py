"""Revenue agent port."""

from __future__ import annotations

from typing import Protocol

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.revenue.models import RevenueAnalysisRequest, RevenueInsights


class RevenueAgentPort(Protocol):
    async def analyze(
        self, request: RevenueAnalysisRequest, context: AgentContext
    ) -> AgentResult[RevenueInsights]: ...
