"""Communication Agent service — one format for every inbound channel."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.errors import AgentValidationError
from app.agents.communication.models import InboundChannel, NormalizedMessage, RawInboundMessage

_WHITESPACE_RE = re.compile(r"\s+")
_SUPPORTED = {c.value for c in InboundChannel}


class CommunicationAgent(Agent[RawInboundMessage, NormalizedMessage]):
    name = "communication"

    async def handle(
        self, payload: RawInboundMessage, context: AgentContext
    ) -> AgentResult[NormalizedMessage]:
        return await self.normalize(payload, context)

    async def normalize(
        self, message: RawInboundMessage, context: AgentContext
    ) -> AgentResult[NormalizedMessage]:
        channel = (message.channel or "").strip().lower()
        if channel not in _SUPPORTED:
            raise AgentValidationError(
                f"Unsupported channel: {message.channel}",
                agent=self.name,
                correlation_id=context.correlation_id,
            )

        body = _WHITESPACE_RE.sub(" ", (message.content or "").strip())
        if not body:
            raise AgentValidationError(
                "Message content cannot be empty",
                agent=self.name,
                correlation_id=context.correlation_id,
            )

        sender = (message.sender_identifier or "").strip() or None
        subject = (message.subject or "").strip() or None
        if channel == InboundChannel.EMAIL.value and not subject:
            subject = "(no subject)"

        received_at = message.received_at or datetime.now(timezone.utc)
        context.channel = channel

        normalized = NormalizedMessage(
            channel=channel,
            direction="incoming",
            body=body,
            sender=sender,
            recipient=None,
            subject=subject,
            received_at=received_at,
            language=_detect_language(body),
            metadata={
                **(message.metadata or {}),
                "attachment_count": len(message.attachments or []),
                "attachments": list(message.attachments or []),
            },
        )
        return AgentResult.ok(normalized)


def _detect_language(text: str) -> str:
    # Lightweight heuristic; swap for a language-detection port later.
    if re.search(r"[áéíóúñ¿¡]", text, re.IGNORECASE):
        return "es"
    return "en"
