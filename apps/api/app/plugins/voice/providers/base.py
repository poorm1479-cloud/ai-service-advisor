"""Voice providers — telephony adapters (no business execution)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class VoiceProviderPort(Protocol):
    provider_id: str

    async def accept_call(self, *, call_sid: str, from_number: str, to_number: str) -> dict[str, Any]: ...

    async def say(self, *, call_sid: str, text: str, voice: str = "alice") -> dict[str, Any]: ...

    async def transfer(self, *, call_sid: str, to_number: str | None = None, reason: str = "") -> dict[str, Any]: ...

    async def hangup(self, *, call_sid: str) -> dict[str, Any]: ...


@dataclass
class FakeVoiceProvider:
    """Local/dev provider — records actions without hitting Twilio."""

    provider_id: str = "fake"
    actions: list[dict[str, Any]] = field(default_factory=list)

    async def accept_call(self, *, call_sid: str, from_number: str, to_number: str) -> dict[str, Any]:
        action = {
            "action": "accept",
            "call_sid": call_sid,
            "from_number": from_number,
            "to_number": to_number,
        }
        self.actions.append(action)
        return {"ok": True, "provider": self.provider_id, **action}

    async def say(self, *, call_sid: str, text: str, voice: str = "alice") -> dict[str, Any]:
        action = {"action": "say", "call_sid": call_sid, "text": text, "voice": voice}
        self.actions.append(action)
        return {"ok": True, "provider": self.provider_id, **action}

    async def transfer(self, *, call_sid: str, to_number: str | None = None, reason: str = "") -> dict[str, Any]:
        action = {
            "action": "transfer",
            "call_sid": call_sid,
            "to_number": to_number or "queue:human",
            "reason": reason,
        }
        self.actions.append(action)
        return {"ok": True, "provider": self.provider_id, **action}

    async def hangup(self, *, call_sid: str) -> dict[str, Any]:
        action = {"action": "hangup", "call_sid": call_sid}
        self.actions.append(action)
        return {"ok": True, "provider": self.provider_id, **action}


@dataclass
class TwilioBridgeProvider:
    """Optional bridge to existing app.voice Twilio provider — adapter only."""

    inner: Any | None = None
    provider_id: str = "twilio_bridge"

    async def accept_call(self, *, call_sid: str, from_number: str, to_number: str) -> dict[str, Any]:
        # Existing provider speaks via TwiML; we only acknowledge at plugin layer
        return {
            "ok": True,
            "provider": self.provider_id,
            "call_sid": call_sid,
            "bridged": self.inner is not None,
            "from_number": from_number,
            "to_number": to_number,
        }

    async def say(self, *, call_sid: str, text: str, voice: str = "alice") -> dict[str, Any]:
        if self.inner is not None and hasattr(self.inner, "say_twiml"):
            twiml = self.inner.say_twiml(text=text, voice=voice)
            return {"ok": True, "provider": self.provider_id, "call_sid": call_sid, "twiml": twiml}
        return {"ok": True, "provider": self.provider_id, "call_sid": call_sid, "text": text, "voice": voice}

    async def transfer(self, *, call_sid: str, to_number: str | None = None, reason: str = "") -> dict[str, Any]:
        return {
            "ok": True,
            "provider": self.provider_id,
            "call_sid": call_sid,
            "to_number": to_number,
            "reason": reason,
            "note": "Transfer signaled — Workflow/human queue handles business routing",
        }

    async def hangup(self, *, call_sid: str) -> dict[str, Any]:
        return {"ok": True, "provider": self.provider_id, "call_sid": call_sid, "action": "hangup"}


def build_default_provider() -> VoiceProviderPort:
    try:
        from app.infrastructure.config import settings

        if getattr(settings, "voice_provider", "fake") != "fake" and getattr(
            settings, "twilio_account_sid", None
        ):
            from app.voice.factory import build_voice_provider

            return TwilioBridgeProvider(inner=build_voice_provider())
    except Exception:  # noqa: BLE001
        pass
    return FakeVoiceProvider()
