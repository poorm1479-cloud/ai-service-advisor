"""Marketing agent ports."""

from __future__ import annotations

from typing import Protocol

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.marketing.models import MarketingActionResult, MarketingRequest


class MarketingDispatcherPort(Protocol):
    async def dispatch(self, action: MarketingActionResult) -> MarketingActionResult: ...


class MarketingAgentPort(Protocol):
    async def execute(
        self, request: MarketingRequest, context: AgentContext
    ) -> AgentResult[MarketingActionResult]: ...
