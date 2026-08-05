"""Voice session lifecycle service — adapter only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.plugins.voice.events import (
    CallCompletedEvent,
    ConversationStartedEvent,
    HumanEscalationEvent,
    IncomingCallEvent,
    VoiceMessageEvent,
)
from app.plugins.voice.metrics import VoiceMetricsCollector
from app.plugins.voice.session.store import VoiceSession, VoiceSessionStore, VoiceTurnRecord


class VoiceSessionService:
    def __init__(
        self,
        store: VoiceSessionStore | None = None,
        metrics: VoiceMetricsCollector | None = None,
    ) -> None:
        self._store = store or VoiceSessionStore()
        self._metrics = metrics or VoiceMetricsCollector()
        self._event_log: list[Any] = []

    @property
    def store(self) -> VoiceSessionStore:
        return self._store

    @property
    def metrics(self) -> VoiceMetricsCollector:
        return self._metrics

    @property
    def events(self) -> list[Any]:
        return list(self._event_log)

    def _emit(self, event: Any) -> Any:
        self._event_log.append(event)
        self._event_log = self._event_log[-500:]
        self._metrics.append_event(event)
        return event

    def receive_call(
        self,
        *,
        shop_id: UUID,
        call_sid: str | None = None,
        from_number: str = "",
        to_number: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        sid = call_sid or f"CA{uuid4().hex[:24]}"
        existing = self._store.get_by_sid(sid)
        if existing:
            return self._session_payload(existing, created=False)

        session = VoiceSession(
            id=uuid4(),
            shop_id=shop_id,
            call_sid=sid,
            from_number=from_number,
            to_number=to_number,
            status="ringing",
            customer_id=kwargs.get("customer_id"),
            metadata=dict(kwargs.get("metadata") or {}),
        )
        self._store.save(session)
        self._metrics.record_call_started()
        event = IncomingCallEvent(
            shop_id=shop_id,
            call_sid=sid,
            from_number=from_number,
            to_number=to_number,
            session_id=session.id,
            payload={"metadata": session.metadata},
        )
        self._emit(event)
        return self._session_payload(session, created=True, event=event)

    def create_session(
        self,
        *,
        shop_id: UUID,
        call_sid: str | None = None,
        from_number: str = "",
        to_number: str = "",
        conversation_id: UUID | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = self.receive_call(
            shop_id=shop_id,
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            customer_id=kwargs.get("customer_id"),
            metadata=kwargs.get("metadata"),
        )
        session = self._store.get(UUID(result["session_id"]))
        assert session is not None
        session.status = "active"
        if conversation_id:
            session.conversation_id = conversation_id
        elif kwargs.get("create_conversation_id", True) and session.conversation_id is None:
            session.conversation_id = uuid4()
        self._store.save(session)
        started = ConversationStartedEvent(
            shop_id=shop_id,
            session_id=session.id,
            conversation_id=session.conversation_id,
            caller_phone=session.from_number,
            payload={"call_sid": session.call_sid},
        )
        self._emit(started)
        out = self._session_payload(session, created=result.get("created", False), event=started)
        out["conversation_started"] = True
        return out

    def append_message(
        self,
        *,
        session_id: UUID,
        role: str,
        text: str,
        audio_url: str | None = None,
        **meta: Any,
    ) -> dict[str, Any]:
        session = self._require(session_id)
        turn = VoiceTurnRecord(
            role=role if role in {"caller", "assistant", "system"} else "caller",  # type: ignore[arg-type]
            text=text,
            audio_url=audio_url,
            metadata=dict(meta),
        )
        session.turns.append(turn)
        session.context["last_role"] = turn.role
        session.context["last_text"] = text
        session.context["turn_count"] = len(session.turns)
        self._store.save(session)
        event = VoiceMessageEvent(
            shop_id=session.shop_id,
            session_id=session.id,
            conversation_id=session.conversation_id,
            role=turn.role,
            text=text,
            payload={"turn_id": str(turn.id), "audio_url": audio_url},
        )
        self._emit(event)
        return {
            "session_id": str(session.id),
            "turn_id": str(turn.id),
            "role": turn.role,
            "text": text,
            "turn_count": len(session.turns),
            "event": event,
        }

    def transfer_to_human(
        self,
        *,
        session_id: UUID,
        reason: str = "customer_request",
    ) -> dict[str, Any]:
        session = self._require(session_id)
        session.human_takeover = True
        session.status = "transferred"
        session.escalation_reason = reason
        self._store.save(session)
        self._metrics.record_transfer(reason)
        event = HumanEscalationEvent(
            shop_id=session.shop_id,
            session_id=session.id,
            conversation_id=session.conversation_id,
            reason=reason,
            payload={"call_sid": session.call_sid},
        )
        self._emit(event)
        # Adapter only — does not mutate CRM / scheduling / send business messages
        return {
            "ok": True,
            "session_id": str(session.id),
            "transferred": True,
            "reason": reason,
            "event": event,
            "business_actions_executed": False,
        }

    def end_call(
        self,
        *,
        session_id: UUID,
        resolved_by_ai: bool | None = None,
        appointment_converted: bool = False,
        satisfaction: float | None = None,
    ) -> dict[str, Any]:
        session = self._require(session_id)
        session.status = "completed"
        session.ended_at = datetime.now(timezone.utc)
        if resolved_by_ai is None:
            resolved_by_ai = not session.human_takeover and len(session.turns) > 0
        session.resolved_by_ai = bool(resolved_by_ai)
        session.appointment_converted = appointment_converted
        if satisfaction is not None:
            session.satisfaction = float(satisfaction)
        self._store.save(session)
        duration = None
        if session.started_at and session.ended_at:
            duration = (session.ended_at - session.started_at).total_seconds()
        self._metrics.record_call_completed(
            resolved_by_ai=session.resolved_by_ai,
            transferred=session.human_takeover,
            appointment_converted=session.appointment_converted,
            satisfaction=session.satisfaction,
        )
        event = CallCompletedEvent(
            shop_id=session.shop_id,
            session_id=session.id,
            conversation_id=session.conversation_id,
            duration_sec=duration,
            resolved_by_ai=session.resolved_by_ai,
            transferred=session.human_takeover,
            appointment_converted=session.appointment_converted,
            satisfaction=session.satisfaction,
            payload={"call_sid": session.call_sid, "turns": len(session.turns)},
        )
        self._emit(event)
        return {
            "ok": True,
            "session_id": str(session.id),
            "status": session.status,
            "duration_sec": duration,
            "event": event,
            "business_actions_executed": False,
        }

    def record_conversation(
        self,
        *,
        session_id: UUID,
        recording_url: str | None = None,
        recording_sid: str | None = None,
    ) -> dict[str, Any]:
        session = self._require(session_id)
        if recording_url:
            session.recording_url = recording_url
        if recording_sid:
            session.recording_sid = recording_sid
        transcript = "\n".join(f"{t.role}: {t.text}" for t in session.turns)
        session.context["transcript"] = transcript
        self._store.save(session)
        return {
            "session_id": str(session.id),
            "conversation_id": str(session.conversation_id) if session.conversation_id else None,
            "recording_url": session.recording_url,
            "recording_sid": session.recording_sid,
            "transcript": transcript,
            "turn_count": len(session.turns),
            # Soft link for Conversation domain — caller may persist via Conversation plugin
            "channel": "phone",
            "business_actions_executed": False,
        }

    def _require(self, session_id: UUID) -> VoiceSession:
        session = self._store.get(session_id)
        if session is None:
            raise LookupError(f"Voice session not found: {session_id}")
        return session

    def _session_payload(
        self,
        session: VoiceSession,
        *,
        created: bool,
        event: Any | None = None,
    ) -> dict[str, Any]:
        return {
            "created": created,
            "session_id": str(session.id),
            "call_sid": session.call_sid,
            "shop_id": str(session.shop_id) if session.shop_id else None,
            "status": session.status,
            "from_number": session.from_number,
            "to_number": session.to_number,
            "conversation_id": str(session.conversation_id) if session.conversation_id else None,
            "event": event,
            "business_actions_executed": False,
        }
