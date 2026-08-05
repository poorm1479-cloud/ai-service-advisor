"""Intent agent port."""

from __future__ import annotations

from typing import Protocol

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.communication.models import NormalizedMessage
from app.agents.intent.models import IntentResult


class IntentAgentPort(Protocol):
    async def detect(
        self, message: NormalizedMessage, context: AgentContext
    ) -> AgentResult[IntentResult]:
        """Detect customer intent and return structured JSON-ready result."""
