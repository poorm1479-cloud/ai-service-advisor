"""Channel adapters — SMS / Email / Voice (fake providers for local + tests)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from app.marketing.enums import Channel
from app.marketing.models import CampaignMessage

logger = logging.getLogger("asa.marketing.channels")


@dataclass(slots=True)
class SendResult:
    ok: bool
    provider_id: str | None = None
    error: str | None = None


class ChannelSender(Protocol):
    channel: Channel

    async def send(self, message: CampaignMessage, *, to: str) -> SendResult: ...


@dataclass
class InMemoryChannelSender:
    channel: Channel
    sent: list[dict] = field(default_factory=list)
    fail_next: int = 0

    async def send(self, message: CampaignMessage, *, to: str) -> SendResult:
        if self.fail_next > 0:
            self.fail_next -= 1
            return SendResult(ok=False, error="transient provider error")
        pid = f"{self.channel.value}_{uuid4().hex[:10]}"
        self.sent.append(
            {
                "provider_id": pid,
                "to": to,
                "body": message.body,
                "subject": message.subject,
                "message_id": str(message.id),
            }
        )
        return SendResult(ok=True, provider_id=pid)


class ConversationMirror(Protocol):
    """Optional bridge into SMS Conversations inbox."""

    async def mirror_outbound(
        self, message: CampaignMessage, *, to: str, provider_id: str | None
    ) -> None: ...


@dataclass
class ConversationBridgingSmsSender:
    """Wrap an SMS channel sender and mirror successful sends into Conversations."""

    inner: ChannelSender
    mirror: ConversationMirror
    channel: Channel = Channel.SMS

    async def send(self, message: CampaignMessage, *, to: str) -> SendResult:
        result = await self.inner.send(message, to=to)
        if not result.ok:
            return result
        try:
            await self.mirror.mirror_outbound(message, to=to, provider_id=result.provider_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "marketing.sms_conversation_mirror_failed message_id=%s: %s",
                message.id,
                exc,
            )
        return result


@dataclass(slots=True)
class ChannelRouter:
    sms: ChannelSender
    email: ChannelSender
    voice: ChannelSender

    def get(self, channel: Channel) -> ChannelSender:
        if channel == Channel.SMS:
            return self.sms
        if channel == Channel.EMAIL:
            return self.email
        return self.voice


def build_default_channels() -> ChannelRouter:
    return ChannelRouter(
        sms=InMemoryChannelSender(Channel.SMS),
        email=InMemoryChannelSender(Channel.EMAIL),
        voice=InMemoryChannelSender(Channel.VOICE),
    )


@dataclass(slots=True)
class SmsServiceConversationMirror:
    """Adapts SmsAiService.mirror_outbound for marketing SMS sends."""

    sms_service: object  # SmsAiService — typed loosely to avoid import cycle

    async def mirror_outbound(
        self, message: CampaignMessage, *, to: str, provider_id: str | None
    ) -> None:
        await self.sms_service.mirror_outbound(  # type: ignore[attr-defined]
            shop_id=message.shop_id,
            to_phone=to,
            body=message.body,
            customer_id=message.customer_id,
            twilio_sid=provider_id,
            intent="marketing",
            owner_summary=f"Marketing campaign {message.campaign_id}",
            metadata={
                "source": "marketing",
                "campaign_id": str(message.campaign_id),
                "marketing_message_id": str(message.id),
            },
        )


def bridge_sms_to_conversations(
    channels: ChannelRouter, *, sms_service: object
) -> ChannelRouter:
    """Return a ChannelRouter whose SMS sender mirrors into Conversations."""
    mirror = SmsServiceConversationMirror(sms_service=sms_service)
    return ChannelRouter(
        sms=ConversationBridgingSmsSender(inner=channels.sms, mirror=mirror),
        email=channels.email,
        voice=channels.voice,
    )
