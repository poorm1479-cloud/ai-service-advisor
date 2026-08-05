"""Channel adapter protocol — transport-only wrappers over existing modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(slots=True)
class ChannelInbound:
    channel: str
    content: str
    sender_identifier: str | None = None
    recipient_identifier: str | None = None
    subject: str | None = None
    attachments: list[str] = field(default_factory=list)
    external_conversation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    channel: str

    def normalize(self, payload: dict[str, Any]) -> ChannelInbound: ...

    async def send(
        self,
        shop_id: UUID,
        *,
        to: str,
        body: str,
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class BaseChannelAdapter:
    channel: str = "unknown"

    def normalize(self, payload: dict[str, Any]) -> ChannelInbound:
        return ChannelInbound(
            channel=self.channel,
            content=str(payload.get("content") or payload.get("body") or ""),
            sender_identifier=payload.get("sender_identifier")
            or payload.get("from")
            or payload.get("from_number"),
            recipient_identifier=payload.get("recipient_identifier")
            or payload.get("to")
            or payload.get("to_number"),
            subject=payload.get("subject"),
            attachments=list(payload.get("attachments") or []),
            external_conversation_id=(
                str(payload["conversation_id"])
                if payload.get("conversation_id")
                else payload.get("external_conversation_id")
            ),
            metadata=dict(payload.get("metadata") or {}),
        )

    async def send(
        self,
        shop_id: UUID,
        *,
        to: str,
        body: str,
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "channel": self.channel,
            "shop_id": str(shop_id),
            "to": to,
            "body": body,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "queued": True,
            "metadata": dict(metadata or {}),
        }
