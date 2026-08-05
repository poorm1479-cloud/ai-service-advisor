"""Campaign suggestion builders — AI MUST NOT send marketing or apply discounts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.agents.decisions.types import (
    CampaignRecommendationDecision,
    ContactTimingDecision,
)


class CampaignDecisionFactory:
    def suggest_campaign(
        self,
        *,
        customer_id: UUID | None,
        campaign_type: str,
        channel: str = "sms",
        message_draft: str = "",
        audience_size: int = 1,
        rationale: str = "",
    ) -> CampaignRecommendationDecision:
        return CampaignRecommendationDecision(
            customer_id=customer_id,
            campaign_type=campaign_type,
            channel=channel,
            message_draft=message_draft,
            audience_size=audience_size,
            auto_send=False,  # hard rule — Workflow records suggestion only
            rationale=rationale or f"Campaign suggestion: {campaign_type}",
        )

    def contact_timing(
        self,
        *,
        customer_id: UUID | None,
        channel: str = "sms",
        preferred_window: str = "weekday_morning",
        reason: str = "",
    ) -> ContactTimingDecision:
        return ContactTimingDecision(
            customer_id=customer_id,
            channel=channel,
            preferred_window=preferred_window,
            reason=reason or "Optimal contact timing from engagement patterns",
            rationale=reason,
        )
