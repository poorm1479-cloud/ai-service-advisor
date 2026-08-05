"""Email channel adapter — wraps MCP EmailAdapter when available."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.conversation.channels.base import BaseChannelAdapter


class EmailChannelAdapter(BaseChannelAdapter):
    channel = "email"

    def __init__(self, email_adapter: Any | None = None) -> None:
        self._email = email_adapter

    async def send(
        self,
        shop_id: UUID,
        *,
        to: str,
        body: str,
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = dict(metadata or {})
        subject = meta.get("subject") or "Message from your shop"
        if self._email is not None:
            try:
                if hasattr(self._email, "send"):
                    await self._email.send(to=to, subject=subject, body=body)
                return {
                    "success": True,
                    "channel": self.channel,
                    "to": to,
                    "subject": subject,
                    "conversation_id": str(conversation_id) if conversation_id else None,
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "channel": self.channel, "error": str(exc)}
        return await super().send(
            shop_id,
            to=to,
            body=body,
            conversation_id=conversation_id,
            metadata={**meta, "subject": subject},
        )
