"""Twilio Voice webhooks — answer, gather speech, status, recording, media stream."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse

from app.infrastructure.config import settings
from app.sms.twilio.provider import parse_twilio_form
from app.voice.factory import VoiceRuntime
from app.voice.models import InboundCallEvent, SpeechInput
from app.voice.runtime import get_voice_runtime

logger = logging.getLogger("asa.voice.webhook")

router = APIRouter(prefix="/v1/webhooks/twilio/voice", tags=["webhooks-voice"])


def _runtime() -> VoiceRuntime:
    return get_voice_runtime()


def _public_url(request: Request, path_suffix: str) -> str:
    if settings.twilio_webhook_public_url:
        return settings.twilio_webhook_public_url.rstrip("/") + path_suffix
    return str(request.url)


@router.post("")
@router.post("/")
async def twilio_voice_answer(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> PlainTextResponse:
    if not settings.voice_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Voice disabled")

    form = await request.form()
    params = parse_twilio_form(dict(form))
    signature = request.headers.get("X-Twilio-Signature")
    url = _public_url(request, "/v1/webhooks/twilio/voice")

    if not runtime.provider.verify_webhook(url=url, params=params, signature=signature):
        runtime.monitor.record_webhook_rejected()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    call_sid = params.get("CallSid", "")
    from_number = params.get("From", "")
    to_number = params.get("To", "")
    if not call_sid or not from_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Missing CallSid/From")

    shop_id = await runtime.service.resolve_shop_id(to_number)
    if shop_id is None:
        # Dev fallback: if only one mapped shop isn't set, reject
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Shop not mapped for this number")

    result = await runtime.service.answer_call(
        shop_id=shop_id,
        event=InboundCallEvent(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            call_status=params.get("CallStatus"),
            direction=params.get("Direction"),
            raw=params,
        ),
    )
    return PlainTextResponse(content=result.twiml, media_type="application/xml")


@router.post("/gather")
async def twilio_voice_gather(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> PlainTextResponse:
    form = await request.form()
    params = parse_twilio_form(dict(form))
    signature = request.headers.get("X-Twilio-Signature")
    url = _public_url(request, "/v1/webhooks/twilio/voice/gather")
    if not runtime.provider.verify_webhook(url=url, params=params, signature=signature):
        runtime.monitor.record_webhook_rejected()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    call_sid = params.get("CallSid", "")
    speech = params.get("SpeechResult", "") or params.get("UnstableSpeechResult", "")
    confidence = params.get("Confidence")
    conf = float(confidence) if confidence not in (None, "") else None

    call = await runtime.store.get_call_by_sid(call_sid)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Call not found")

    result = await runtime.service.handle_speech(
        shop_id=call.shop_id,
        speech=SpeechInput(
            call_sid=call_sid,
            speech_result=speech,
            confidence=conf,
            interrupted=params.get("SpeechResult") is None and bool(params.get("UnstableSpeechResult")),
            raw=params,
        ),
    )
    return PlainTextResponse(content=result.twiml, media_type="application/xml")


@router.post("/status")
async def twilio_voice_status(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> dict[str, str]:
    form = await request.form()
    params = parse_twilio_form(dict(form))
    call_sid = params.get("CallSid", "")
    call_status = (params.get("CallStatus") or "").lower()
    call = await runtime.store.get_call_by_sid(call_sid)
    if call and call_status in {"completed", "busy", "no-answer", "failed", "canceled"}:
        await runtime.service.complete_call(shop_id=call.shop_id, call_id=call.id)
    return {"status": "ok"}


@router.post("/recording")
async def twilio_voice_recording(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> dict[str, str]:
    form = await request.form()
    params = parse_twilio_form(dict(form))
    call_sid = params.get("CallSid", "")
    recording_sid = params.get("RecordingSid", "")
    recording_url = params.get("RecordingUrl", "")
    duration = params.get("RecordingDuration")
    duration_sec = int(duration) if duration and str(duration).isdigit() else None
    await runtime.service.store_recording_metadata(
        call_sid=call_sid,
        recording_sid=recording_sid,
        recording_url=recording_url,
        duration_sec=duration_sec,
    )
    return {"status": "ok"}


@router.websocket("/stream")
async def twilio_voice_stream(websocket: WebSocket) -> None:
    """Twilio Media Streams websocket — streaming audio support."""
    await websocket.accept()
    runtime = get_voice_runtime()
    try:
        while True:
            data = await websocket.receive_json()
            chunk = runtime.streams.handle_event(data)
            if chunk and chunk.event_type == "interrupt":
                call = await runtime.store.get_call_by_sid(chunk.call_sid)
                if call:
                    await runtime.memory.mark_interrupted(
                        shop_id=call.shop_id, call_id=call.id
                    )
            if chunk and chunk.event_type == "stop":
                break
    except WebSocketDisconnect:
        logger.info("voice.stream.disconnected")
    except Exception:  # noqa: BLE001
        logger.exception("voice.stream.error")
        await websocket.close()


@router.get("/health")
async def voice_webhook_health(runtime: VoiceRuntime = Depends(_runtime)) -> dict[str, Any]:
    return {
        "voice_enabled": settings.voice_enabled,
        "provider": settings.voice_provider,
        "stream_enabled": settings.voice_stream_enabled,
        "queue_depth": await runtime.queue.depth(),
        "metrics": runtime.monitor.snapshot(),
        "live_streams": len(runtime.streams.sessions),
    }
