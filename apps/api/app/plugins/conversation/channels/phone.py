"""Phone / Voice channel adapter — wraps VoiceAiService (no rewrite)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.conversation.channels.base import BaseChannelAdapter, ChannelInbound


class PhoneChannelAdapter(BaseChannelAdapter):
    channel = "phone"

    def __init__(self, voice_service: Any | None = None) -> None:
        self._voice = voice_service

    def normalize(self, payload: dict[str, Any]) -> ChannelInbound:
        inbound = super().normalize(payload)
        inbound.channel = self.channel
        # Voice calls use call_id as external conversation key when present
        call_id = payload.get("call_id") or (inbound.metadata or {}).get("call_id")
        if call_id and not inbound.external_conversation_id:
            inbound.external_conversation_id = str(call_id)
        return inbound

    async def send(
        self,
        shop_id: UUID,
        *,
        to: str,
        body: str,
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Voice outbound is TwiML/TTS driven; record intent to speak
        return {
            "success": True,
            "channel": self.channel,
            "shop_id": str(shop_id),
            "to": to,
            "spoken_text": body,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "voice_service_bound": self._voice is not None,
            "metadata": dict(metadata or {}),
        }


# Alias for clarity in diagrams / future imports
VoiceChannelAdapter = PhoneChannelAdapter
