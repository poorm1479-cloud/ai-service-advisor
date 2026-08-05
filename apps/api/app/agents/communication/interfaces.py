"""Communication agent port."""

from __future__ import annotations

from typing import Protocol

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.communication.models import NormalizedMessage, RawInboundMessage


class CommunicationAgentPort(Protocol):
    async def normalize(
        self, message: RawInboundMessage, context: AgentContext
    ) -> AgentResult[NormalizedMessage]:
        """Normalize a raw inbound message into the canonical format."""
