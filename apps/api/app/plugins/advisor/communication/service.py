"""Customer communication — decide only (compose replies / explanations)."""

from __future__ import annotations

from typing import Any

from app.agents.decisions.types import (
    CustomerCommunicationDecision,
    RepairRecommendationDecision,
)
from app.plugins.advisor.models import AdvisorContext


class AdvisorCommunicationService:
    def generate_customer_explanation(
        self, ctx: AdvisorContext, *, recommendations: list[RepairRecommendationDecision] | None = None
    ) -> list[Any]:
        recs = recommendations or []
        if recs:
            body = recs[0].plain_language or recs[0].description
        elif ctx.inbound_text:
            body = (
                "Thanks for reaching out. We're reviewing your vehicle details and will "
                "recommend the safest next step shortly."
            )
        else:
            return []
        return [
            CustomerCommunicationDecision(
                customer_id=ctx.customer_id,
                conversation_id=_conv_uuid(ctx),
                channel=ctx.channel or "sms",
                body=body,
                intent=ctx.intent,
                tone="plain_language",
                confidence=0.8,
                rationale="Customer-friendly explanation",
            )
        ]

    def generate_reply(self, ctx: AdvisorContext, *, body: str | None = None) -> list[Any]:
        text = body or (
            "Got it — our service advisor team is on it and will keep you updated."
        )
        return [
            CustomerCommunicationDecision(
                customer_id=ctx.customer_id,
                conversation_id=_conv_uuid(ctx),
                channel=ctx.channel or "sms",
                body=text,
                intent=ctx.intent,
                confidence=0.7,
                rationale="Advisor customer reply plan",
            )
        ]


def _conv_uuid(ctx: AdvisorContext):
    from uuid import UUID

    if not ctx.conversation_id:
        return None
    try:
        return UUID(str(ctx.conversation_id))
    except (ValueError, TypeError):
        return None
