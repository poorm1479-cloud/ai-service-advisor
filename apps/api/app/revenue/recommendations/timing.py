"""Contact timing recommendations — analysis only, never sends messages."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.revenue.decisions.campaign import CampaignDecisionFactory


class ContactTimingService:
    def __init__(self) -> None:
        self._factory = CampaignDecisionFactory()

    async def recommend_contact_timing(
        self,
        shop_id: UUID,
        *,
        customer_id: UUID | None = None,
        channel: str = "sms",
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prefs = preferences or {}
        window = str(
            prefs.get("preferred_window")
            or prefs.get("contact_window")
            or "weekday_morning"
        )
        decision = self._factory.contact_timing(
            customer_id=customer_id,
            channel=channel,
            preferred_window=window,
            reason="Derived from shop/customer communication preferences",
        )
        return {
            "shop_id": str(shop_id),
            "decision": decision,
            "preferred_window": window,
            "channel": channel,
            "ai_actions_allowed": False,
            "note": "Suggestion only — Workflow must not auto-send from this capability",
        }
