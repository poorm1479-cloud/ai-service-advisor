"""Voice call dashboard API — live calls, history, transcript, summary."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, require_capabilities
from app.core.permissions.capabilities import StaffCapability
from app.infrastructure.config import settings
from app.voice.factory import VoiceRuntime
from app.voice.models import InboundCallEvent, SpeechInput
from app.voice.runtime import get_voice_runtime
from app.voice.store import InMemoryVoiceStore

router = APIRouter(prefix="/v1/voice", tags=["voice"])

_require_comms = require_capabilities(StaffCapability.CUSTOMER_COMMUNICATION)


def _runtime() -> VoiceRuntime:
    return get_voice_runtime()


class CallOut(BaseModel):
    id: UUID
    shop_id: UUID
    caller_phone: str
    called_phone: str
    status: str
    customer_id: UUID | None
    twilio_call_sid: str | None
    recording_url: str | None
    recording_duration_sec: int | None
    last_intent: str | None
    call_summary: str | None
    owner_summary: str | None
    escalate: bool
    escalation_reason: str | None
    human_takeover: bool
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime | None


class TurnOut(BaseModel):
    id: UUID
    role: str
    text: str
    intent: str | None
    interrupted: bool
    created_at: datetime | None


class CallDetailOut(BaseModel):
    call: CallOut
    turns: list[TurnOut]
    transcript: str | None
    call_summary: str | None
    repair_notes: dict[str, Any] | None
    owner_summary: str | None


class TakeoverRequest(BaseModel):
    enabled: bool = True


class SimulateCallRequest(BaseModel):
    from_number: str
    utterances: list[str] = Field(min_length=1)
    to_number: str | None = None


class StartChatRequest(BaseModel):
    """Start an interactive caller-side chat (same pipeline as a live phone call)."""

    from_number: str
    to_number: str | None = None


class ChatMessageRequest(BaseModel):
    """One turn as the caller — AI replies and the call stays open until farewell."""

    text: str = Field(min_length=1, max_length=2000)


def _call_out(c) -> CallOut:
    return CallOut(
        id=c.id,
        shop_id=c.shop_id,
        caller_phone=c.caller_phone,
        called_phone=c.called_phone,
        status=c.status,
        customer_id=c.customer_id,
        twilio_call_sid=c.twilio_call_sid,
        recording_url=c.recording_url,
        recording_duration_sec=c.recording_duration_sec,
        last_intent=c.last_intent,
        call_summary=c.call_summary,
        owner_summary=c.owner_summary,
        escalate=c.escalate,
        escalation_reason=c.escalation_reason,
        human_takeover=c.human_takeover,
        started_at=c.started_at,
        ended_at=c.ended_at,
        created_at=c.created_at,
    )


def _turn_out(t) -> TurnOut:
    return TurnOut(
        id=t.id,
        role=t.role,
        text=t.text,
        intent=t.intent,
        interrupted=t.interrupted,
        created_at=t.created_at,
    )


async def _detail_out(runtime: VoiceRuntime, shop_id: UUID, call_id: UUID) -> CallDetailOut:
    call = await runtime.store.get_call(shop_id, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")
    turns = await runtime.store.list_turns(shop_id, call_id)
    return CallDetailOut(
        call=_call_out(call),
        turns=[_turn_out(t) for t in turns],
        transcript=call.transcript,
        call_summary=call.call_summary,
        repair_notes=call.repair_notes,
        owner_summary=call.owner_summary,
    )


def _ensure_dev_simulate_allowed() -> None:
    if settings.environment == "production" and settings.voice_provider == "twilio":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Simulate chat disabled in production"
        )


@router.get("/live", response_model=list[CallOut])
async def list_live_calls(
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> list[CallOut]:
    items = await runtime.store.list_live_calls(user.shop_id)
    return [_call_out(c) for c in items]


@router.get("/calls", response_model=list[CallOut])
async def list_calls(
    status_filter: str | None = None,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> list[CallOut]:
    items = await runtime.store.list_calls(user.shop_id, status=status_filter, limit=100)
    return [_call_out(c) for c in items]


@router.get("/calls/{call_id}", response_model=CallDetailOut)
async def get_call(
    call_id: UUID,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallDetailOut:
    call = await runtime.store.get_call(user.shop_id, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")
    turns = await runtime.store.list_turns(user.shop_id, call_id)
    return CallDetailOut(
        call=_call_out(call),
        turns=[_turn_out(t) for t in turns],
        transcript=call.transcript,
        call_summary=call.call_summary,
        repair_notes=call.repair_notes,
        owner_summary=call.owner_summary,
    )


@router.post("/calls/{call_id}/takeover", response_model=CallOut)
async def human_takeover(
    call_id: UUID,
    body: TakeoverRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallOut:
    try:
        call = await runtime.service.set_human_takeover(
            shop_id=user.shop_id, call_id=call_id, enabled=body.enabled
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _call_out(call)


@router.post("/calls/{call_id}/complete", response_model=CallDetailOut)
async def complete_call(
    call_id: UUID,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallDetailOut:
    try:
        call = await runtime.service.complete_call(shop_id=user.shop_id, call_id=call_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    turns = await runtime.store.list_turns(user.shop_id, call_id)
    return CallDetailOut(
        call=_call_out(call),
        turns=[_turn_out(t) for t in turns],
        transcript=call.transcript,
        call_summary=call.call_summary,
        repair_notes=call.repair_notes,
        owner_summary=call.owner_summary,
    )


@router.delete("/calls/{call_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_call(
    call_id: UUID,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> None:
    try:
        await runtime.service.delete_call(shop_id=user.shop_id, call_id=call_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/metrics")
async def voice_metrics(
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return {
        "metrics": runtime.monitor.snapshot(),
        "queue_depth": await runtime.queue.depth(),
        "provider": settings.voice_provider,
        "live_streams": len(runtime.streams.sessions),
    }


@router.post("/chat/start", response_model=CallDetailOut)
async def start_caller_chat(
    body: StartChatRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallDetailOut:
    """Open a continuous call-style chat as the customer (greeting only; stays live)."""
    _ensure_dev_simulate_allowed()

    to_number = body.to_number or settings.twilio_from_number or "+15550001111"
    if isinstance(runtime.store, InMemoryVoiceStore):
        runtime.store.register_shop_number(user.shop_id, to_number)

    call_sid = f"CA{uuid4().hex[:30]}"
    result = await runtime.service.answer_call(
        shop_id=user.shop_id,
        event=InboundCallEvent(
            call_sid=call_sid,
            from_number=body.from_number,
            to_number=to_number,
        ),
    )
    call = result.call
    call.metadata = {
        **(call.metadata or {}),
        "interactive_chat": True,
        "channel": "caller_chat",
    }
    await runtime.store.update_call(call)
    return await _detail_out(runtime, user.shop_id, call.id)


@router.post("/calls/{call_id}/message", response_model=CallDetailOut)
async def send_caller_chat_message(
    call_id: UUID,
    body: ChatMessageRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallDetailOut:
    """Send one customer utterance; call ends only on farewell / hang-up path."""
    _ensure_dev_simulate_allowed()

    call = await runtime.store.get_call(user.shop_id, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")
    if call.ended_at or call.status in {
        "completed",
        "failed",
        "no-answer",
        "no_answer",
        "busy",
        "canceled",
        "cancelled",
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This call has already ended — start a new conversation",
        )
    if not call.twilio_call_sid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Call has no session id"
        )

    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Message text required")

    await runtime.service.handle_speech(
        shop_id=user.shop_id,
        speech=SpeechInput(call_sid=call.twilio_call_sid, speech_result=text),
    )
    return await _detail_out(runtime, user.shop_id, call_id)


@router.post("/simulate", response_model=CallDetailOut)
async def simulate_call(
    body: SimulateCallRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: VoiceRuntime = Depends(_runtime),
) -> CallDetailOut:
    """Batch multi-utterance simulator. Prefer /chat/start + /message for UI chat."""
    _ensure_dev_simulate_allowed()

    to_number = body.to_number or settings.twilio_from_number or "+15550001111"
    if isinstance(runtime.store, InMemoryVoiceStore):
        runtime.store.register_shop_number(user.shop_id, to_number)

    call_sid = f"CA{uuid4().hex[:30]}"
    await runtime.service.answer_call(
        shop_id=user.shop_id,
        event=InboundCallEvent(
            call_sid=call_sid,
            from_number=body.from_number,
            to_number=to_number,
        ),
    )
    call = await runtime.store.get_call_by_sid(call_sid)
    assert call is not None

    for utterance in body.utterances:
        await runtime.service.handle_speech(
            shop_id=user.shop_id,
            speech=SpeechInput(call_sid=call_sid, speech_result=utterance),
        )
        # Mirror live phone: keep open after booking; only farewell completes.
        refreshed = await runtime.store.get_call(user.shop_id, call.id)
        if refreshed and (refreshed.ended_at or refreshed.status == "completed"):
            break

    call = await runtime.store.get_call(user.shop_id, call.id)
    assert call is not None
    # If the script never said goodbye, leave the call live (same as phone).
    return await _detail_out(runtime, user.shop_id, call.id)
