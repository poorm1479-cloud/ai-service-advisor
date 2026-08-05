"""SMS channel adapter — wraps existing SmsAiService / provider (no rewrite)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.conversation.channels.base import BaseChannelAdapter, ChannelInbound


class SmsChannelAdapter(BaseChannelAdapter):
    channel = "sms"

    def __init__(self, sms_service: Any | None = None) -> None:
        self._sms = sms_service

    def normalize(self, payload: dict[str, Any]) -> ChannelInbound:
        inbound = super().normalize(payload)
        inbound.channel = self.channel
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
        if self._sms is not None and hasattr(self._sms, "send_manual_reply"):
            try:
                result = await self._sms.send_manual_reply(
                    shop_id=shop_id,
                    conversation_id=conversation_id,
                    body=body,
                    to_number=to,
                )
                return {
                    "success": True,
                    "channel": self.channel,
                    "result": result,
                    "conversation_id": str(conversation_id) if conversation_id else None,
                }
            except TypeError:
                # Signature variance across implementations
                pass
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "channel": self.channel, "error": str(exc)}
        return await super().send(
            shop_id,
            to=to,
            body=body,
            conversation_id=conversation_id,
            metadata=metadata,
        )
