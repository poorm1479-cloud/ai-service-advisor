"""VoicePlugin — Production Voice AI Integration (communication adapter only).

Voice never executes business actions (CRM / scheduling / payments / approvals).
It converts calls ↔ text, maintains sessions, and hands text to Conversation /
Advisor for Decision Objects. Workflow Engine applies decisions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.voice.metrics import VoiceMetricsCollector
from app.plugins.voice.providers.base import VoiceProviderPort, build_default_provider
from app.plugins.voice.session.service import VoiceSessionService
from app.plugins.voice.session.store import VoiceSessionStore
from app.plugins.voice.speech.service import SpeechService, build_default_speech


class VoicePlugin:
    """IPlugin — Voice is only a communication adapter."""

    def __init__(
        self,
        *,
        store: VoiceSessionStore | None = None,
        metrics: VoiceMetricsCollector | None = None,
        sessions: VoiceSessionService | None = None,
        speech: SpeechService | None = None,
        provider: VoiceProviderPort | None = None,
    ) -> None:
        self._store = store or VoiceSessionStore()
        self._metrics = metrics or VoiceMetricsCollector()
        self._sessions = sessions or VoiceSessionService(store=self._store, metrics=self._metrics)
        self._speech = speech or build_default_speech(self._metrics)
        self._provider = provider or build_default_provider()
        self._initialized = False

    def plugin_id(self) -> str:
        return "voice"

    def plugin_name(self) -> str:
        return "Production Voice AI"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Voice communication adapter: calls, STT/TTS, sessions, recording, "
            "and human transfer. Never executes business actions — Advisor decides, "
            "Workflow executes."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.RECEIVE_CALL.value,
            Capability.CREATE_VOICE_SESSION.value,
            Capability.SPEECH_TO_TEXT.value,
            Capability.TEXT_TO_SPEECH.value,
            Capability.TRANSFER_TO_HUMAN.value,
            Capability.END_CALL.value,
            Capability.RECORD_CONVERSATION.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "provider": getattr(self._provider, "provider_id", type(self._provider).__name__),
            "metrics": self._metrics.snapshot(),
        }

    @property
    def sessions(self) -> VoiceSessionService:
        return self._sessions

    @property
    def metrics(self) -> VoiceMetricsCollector:
        return self._metrics

    async def advise_from_utterance(
        self,
        *,
        shop_id: UUID,
        text: str,
        session_id: UUID | None = None,
        customer_id: UUID | None = None,
        channel: str = "phone",
    ) -> dict[str, Any]:
        """Optional bridge: ask Advisor for Decision Objects only (no apply)."""
        try:
            from app.plugins.framework.context import PluginContext as PC
            from app.plugins.framework.factory import invoke_capability

            out = await invoke_capability(
                Capability.ANALYZE_CONVERSATION.value,
                context=PC.for_shop(shop_id),
                shop_id=shop_id,
                channel=channel,
                inbound_text=text,
                customer_id=customer_id,
                conversation_id=str(session_id) if session_id else None,
            )
            return {
                "decisions": out.get("decisions") or [],
                "advisor_notes": out.get("advisor_notes"),
                "applied": False,
                "business_actions_executed": False,
                "note": "Decisions returned for Workflow Engine — Voice does not apply them",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "decisions": [],
                "applied": False,
                "business_actions_executed": False,
                "error": str(exc),
            }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        shop_id = kwargs.get("shop_id") or (context.shop_id if context else None)
        payload = {k: v for k, v in kwargs.items() if k != "shop_id"}
        cap = capability if isinstance(capability, str) else str(capability)

        if cap in {Capability.RECEIVE_CALL.value, "ReceiveCall"}:
            if shop_id is None:
                raise ValueError("shop_id required for ReceiveCall")
            if isinstance(shop_id, str):
                shop_id = UUID(shop_id)
            result = self._sessions.receive_call(
                shop_id=shop_id,
                call_sid=payload.get("call_sid"),
                from_number=payload.get("from_number") or payload.get("from") or "",
                to_number=payload.get("to_number") or payload.get("to") or "",
                customer_id=payload.get("customer_id"),
                metadata=payload.get("metadata"),
            )
            await self._provider.accept_call(
                call_sid=result["call_sid"],
                from_number=result.get("from_number") or "",
                to_number=result.get("to_number") or "",
            )
            return result

        if cap in {Capability.CREATE_VOICE_SESSION.value, "CreateVoiceSession"}:
            if shop_id is None:
                raise ValueError("shop_id required for CreateVoiceSession")
            if isinstance(shop_id, str):
                shop_id = UUID(shop_id)
            conversation_id = payload.get("conversation_id")
            if isinstance(conversation_id, str):
                conversation_id = UUID(conversation_id)
            return self._sessions.create_session(
                shop_id=shop_id,
                call_sid=payload.get("call_sid"),
                from_number=payload.get("from_number") or payload.get("from") or "",
                to_number=payload.get("to_number") or payload.get("to") or "",
                conversation_id=conversation_id,
                customer_id=payload.get("customer_id"),
                metadata=payload.get("metadata"),
            )

        if cap in {Capability.SPEECH_TO_TEXT.value, "SpeechToText"}:
            stt = await self._speech.speech_to_text(**payload)
            session_id = payload.get("session_id")
            if session_id and stt.get("text"):
                if isinstance(session_id, str):
                    session_id = UUID(session_id)
                self._sessions.append_message(
                    session_id=session_id,
                    role="caller",
                    text=stt["text"],
                )
                if payload.get("request_advice") and shop_id:
                    if isinstance(shop_id, str):
                        shop_id = UUID(shop_id)
                    advice = await self.advise_from_utterance(
                        shop_id=shop_id,
                        text=stt["text"],
                        session_id=session_id,
                        customer_id=payload.get("customer_id"),
                    )
                    stt["advisor"] = advice
            return stt

        if cap in {Capability.TEXT_TO_SPEECH.value, "TextToSpeech"}:
            text = str(payload.get("text") or "")
            tts = await self._speech.text_to_speech(
                text=text,
                voice=payload.get("voice") or "alice",
            )
            session_id = payload.get("session_id")
            if session_id and text:
                if isinstance(session_id, str):
                    session_id = UUID(session_id)
                self._sessions.append_message(
                    session_id=session_id,
                    role="assistant",
                    text=text,
                    audio_url=tts.get("audio_url"),
                )
                call_sid = payload.get("call_sid")
                if call_sid:
                    await self._provider.say(call_sid=str(call_sid), text=text)
            return tts

        if cap in {Capability.TRANSFER_TO_HUMAN.value, "TransferToHuman"}:
            session_id = payload.get("session_id")
            if session_id is None:
                raise ValueError("session_id required for TransferToHuman")
            if isinstance(session_id, str):
                session_id = UUID(session_id)
            result = self._sessions.transfer_to_human(
                session_id=session_id,
                reason=str(payload.get("reason") or "customer_request"),
            )
            session = self._store.get(session_id)
            if session:
                await self._provider.transfer(
                    call_sid=session.call_sid,
                    to_number=payload.get("to_number"),
                    reason=result["reason"],
                )
            return result

        if cap in {Capability.END_CALL.value, "EndCall"}:
            session_id = payload.get("session_id")
            if session_id is None:
                raise ValueError("session_id required for EndCall")
            if isinstance(session_id, str):
                session_id = UUID(session_id)
            result = self._sessions.end_call(
                session_id=session_id,
                resolved_by_ai=payload.get("resolved_by_ai"),
                appointment_converted=bool(payload.get("appointment_converted")),
                satisfaction=payload.get("satisfaction"),
            )
            session = self._store.get(session_id)
            if session:
                await self._provider.hangup(call_sid=session.call_sid)
            return result

        if cap in {Capability.RECORD_CONVERSATION.value, "RecordConversation"}:
            session_id = payload.get("session_id")
            if session_id is None:
                raise ValueError("session_id required for RecordConversation")
            if isinstance(session_id, str):
                session_id = UUID(session_id)
            recorded = self._sessions.record_conversation(
                session_id=session_id,
                recording_url=payload.get("recording_url"),
                recording_sid=payload.get("recording_sid"),
            )
            # Soft-link Conversation domain without applying AI decisions
            if payload.get("persist_conversation") and shop_id:
                try:
                    from app.plugins.framework.factory import invoke_capability

                    if isinstance(shop_id, str):
                        shop_id = UUID(shop_id)
                    conv = await invoke_capability(
                        Capability.CREATE_CONVERSATION.value,
                        context=PluginContext.for_shop(shop_id),
                        shop_id=shop_id,
                        channel="phone",
                        external_id=recorded.get("session_id"),
                        customer_id=payload.get("customer_id"),
                        metadata={
                            "voice_session_id": recorded.get("session_id"),
                            "transcript": recorded.get("transcript"),
                            "recording_url": recorded.get("recording_url"),
                        },
                    )
                    recorded["conversation"] = conv
                except Exception as exc:  # noqa: BLE001
                    recorded["conversation_error"] = str(exc)
            recorded["business_actions_executed"] = False
            return recorded

        raise LookupError(f"Unsupported voice capability: {cap}")
