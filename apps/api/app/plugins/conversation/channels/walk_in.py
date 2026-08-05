"""Walk-in channel adapter — session for counter visits (not a chat transport)."""

from __future__ import annotations

from typing import Any

from app.plugins.conversation.channels.base import BaseChannelAdapter, ChannelInbound


class WalkInChannelAdapter(BaseChannelAdapter):
    channel = "walk_in"

    def normalize(self, payload: dict[str, Any]) -> ChannelInbound:
        inbound = super().normalize(payload)
        inbound.channel = self.channel
        if not inbound.content:
            inbound.content = str(payload.get("note") or "Walk-in check-in")
        walk_in_id = payload.get("walk_in_id") or payload.get("visit_id")
        if walk_in_id and not inbound.external_conversation_id:
            inbound.external_conversation_id = str(walk_in_id)
        return inbound
