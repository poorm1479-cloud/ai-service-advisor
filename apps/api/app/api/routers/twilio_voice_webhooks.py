"""Twilio Voice webhooks — answer, gather speech, status, recording, media stream."""

from __future__ import annotations

import asyncio
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

# Twilio Voice webhook hard timeout is ~15s; leave headroom for TwiML response.
_GATHER_HANDLE_TIMEOUT_SEC = 12.0


def _runtime() -> VoiceRuntime:
    return get_voice_runtime()


def _signature_urls(request: Request, path_suffix: str) -> tuple[str, list[str]]:
    """Primary + alt absolute URLs Twilio may have signed."""
    alts: list[str] = [str(request.url)]
    path = request.url.path or path_suffix
    query = request.url.query
    base = settings.twilio_public_base_url
    if base:
        primary = base + path_suffix
        for p in {path_suffix, path, path.rstrip("/") or path_suffix}:
            u = base + (p if p.startswith("/") else f"/{p}")
            if query:
                u = f"{u}?{query}"
            alts.append(u)
        if query and "?" not in primary:
            alts.append(f"{primary}?{query}")
        # Also accept misconfigured full-path public URL as it was stored historically
        raw = (settings.twilio_webhook_public_url or "").rstrip("/")
        if raw and raw != base:
            alts.append(raw)
            alts.append(raw + path_suffix if not raw.endswith(path_suffix) else raw)
        return primary, alts
    return str(request.url), alts


def _gather_action_url() -> str:
    base = settings.twilio_public_base_url
    path = "/v1/webhooks/twilio/voice/gather"
    return f"{base}{path}" if base else path


def _fallback_gather_twiml(runtime: VoiceRuntime, *, say_text: str) -> str:
    return runtime.provider.build_gather_twiml(
        say_text=say_text,
        action_url=_gather_action_url(),
        barge_in=True,
    )


@router.post("")
@router.post("/")
async def twilio_voice_answer(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> PlainTextResponse:
    if not settings.voice_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Voice disabled")

    form = await request.form()
    params = parse_twilio_form(form)
    signature = request.headers.get("X-Twilio-Signature")
    url, alt_urls = _signature_urls(request, "/v1/webhooks/twilio/voice")

    if not runtime.provider.verify_webhook(
        url=url, params=params, signature=signature, alt_urls=alt_urls
    ):
        runtime.monitor.record_webhook_rejected()
        logger.warning(
            "voice.webhook.rejected signature url=%s path=%s has_sig=%s",
            url,
            request.url.path,
            bool(signature),
        )
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
    """Never return non-TwiML HTTP errors — Twilio hangs up on 4xx/5xx."""
    form = await request.form()
    params = parse_twilio_form(form)
    signature = request.headers.get("X-Twilio-Signature")
    url, alt_urls = _signature_urls(request, "/v1/webhooks/twilio/voice/gather")
    if not runtime.provider.verify_webhook(
        url=url, params=params, signature=signature, alt_urls=alt_urls
    ):
        runtime.monitor.record_webhook_rejected()
        logger.warning(
            "voice.webhook.gather.rejected signature url=%s has_sig=%s",
            url,
            bool(signature),
        )
        # Soft-fail local signature issues so the call stays up for re-listen.
        return PlainTextResponse(
            content=_fallback_gather_twiml(
                runtime,
                say_text="Sorry, I hit a snag. Could you say that again?",
            ),
            media_type="application/xml",
        )

    call_sid = params.get("CallSid", "")
    speech = params.get("SpeechResult", "") or params.get("UnstableSpeechResult", "")
    confidence = params.get("Confidence")
    conf = float(confidence) if confidence not in (None, "") else None
    from_number = params.get("From", "")
    to_number = params.get("To", "")

    try:
        call = await runtime.service.ensure_call_for_sid(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
        )
        if call is None:
            logger.warning(
                "voice.webhook.gather.no_call sid=%s to=%s from=%s",
                call_sid,
                to_number,
                from_number,
            )
            return PlainTextResponse(
                content=_fallback_gather_twiml(
                    runtime,
                    say_text="Sorry, I lost the connection for a moment. How can I help?",
                ),
                media_type="application/xml",
            )

        logger.info(
            "voice.webhook.gather sid=%s speech_chars=%s conf=%s",
            call_sid,
            len(speech or ""),
            conf,
        )
        result = await asyncio.wait_for(
            runtime.service.handle_speech(
                shop_id=call.shop_id,
                speech=SpeechInput(
                    call_sid=call_sid,
                    speech_result=speech,
                    confidence=conf,
                    interrupted=params.get("SpeechResult") is None
                    and bool(params.get("UnstableSpeechResult")),
                    raw=params,
                ),
            ),
            timeout=_GATHER_HANDLE_TIMEOUT_SEC,
        )
        return PlainTextResponse(content=result.twiml, media_type="application/xml")
    except asyncio.TimeoutError:
        logger.warning(
            "voice.webhook.gather.timeout sid=%s after=%ss",
            call_sid,
            _GATHER_HANDLE_TIMEOUT_SEC,
        )
        return PlainTextResponse(
            content=_fallback_gather_twiml(
                runtime,
                say_text="Sorry, that took a second longer than expected. Could you repeat that?",
            ),
            media_type="application/xml",
        )
    except Exception:  # noqa: BLE001 — keep the phone call alive
        logger.exception("voice.webhook.gather.error sid=%s", call_sid)
        return PlainTextResponse(
            content=_fallback_gather_twiml(
                runtime,
                say_text="Sorry, I didn't catch that. Could you say it again?",
            ),
            media_type="application/xml",
        )


@router.post("/status")
async def twilio_voice_status(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> dict[str, str]:
    """Twilio Call Status Changes — fires when the remote party hangs up.

    Configure on the Twilio phone number: Status Callback URL →
    ``{TWILIO_WEBHOOK_PUBLIC_URL}/v1/webhooks/twilio/voice/status``
    (Method POST; events: completed, busy, no-answer, failed, canceled).
    """
    form = await request.form()
    params = parse_twilio_form(form)
    call_sid = params.get("CallSid", "")
    call_status = (params.get("CallStatus") or "").lower()
    # Inbound: To = shop number. Outbound / edge cases may use Called.
    to_number = (
        params.get("To", "")
        or params.get("Called", "")
        or params.get("CalledVia", "")
    )
    terminal = {"completed", "busy", "no-answer", "failed", "canceled", "cancelled"}
    if call_sid and call_status in terminal:
        try:
            call = await runtime.service.complete_call_by_sid(
                call_sid=call_sid,
                final_status=call_status,
                to_number=to_number or None,
            )
            if call is None:
                logger.info(
                    "voice.webhook.status.unknown_sid sid=%s status=%s to=%s keys=%s",
                    call_sid,
                    call_status,
                    to_number,
                    sorted(params.keys()),
                )
            else:
                logger.info(
                    "voice.webhook.status.closed sid=%s status=%s call=%s",
                    call_sid,
                    call.status,
                    call.id,
                )
        except Exception:  # noqa: BLE001 — always 200 so Twilio does not retry forever
            logger.exception(
                "voice.webhook.status.error sid=%s status=%s",
                call_sid,
                call_status,
            )
    return {"status": "ok"}


@router.post("/recording")
async def twilio_voice_recording(
    request: Request,
    runtime: VoiceRuntime = Depends(_runtime),
) -> dict[str, str]:
    form = await request.form()
    params = parse_twilio_form(form)
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
    """Twilio Media Streams websocket — streaming audio support.

    Twilio emits stream ``stop`` when the call ends (remote hang-up included).
    Use that as a secondary complete signal when Status Callback is delayed or
    missing. Also complete on WebSocket disconnect if stop never arrived.
    """
    await websocket.accept()
    runtime = get_voice_runtime()
    active_sid: str | None = None
    active_shop = None
    active_to: str | None = None
    completed = False

    async def _close_active(reason: str) -> None:
        nonlocal completed
        if completed or not active_sid:
            return
        try:
            call = await runtime.service.complete_call_by_sid(
                call_sid=active_sid,
                final_status="completed",
                to_number=active_to,
                shop_id=active_shop,
            )
            completed = True
            if call:
                logger.info(
                    "voice.stream.%s.closed sid=%s call=%s status=%s",
                    reason,
                    active_sid,
                    call.id,
                    call.status,
                )
            else:
                logger.warning(
                    "voice.stream.%s.miss sid=%s shop=%s to=%s",
                    reason,
                    active_sid,
                    active_shop,
                    active_to,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "voice.stream.%s.complete_failed sid=%s", reason, active_sid
            )

    try:
        while True:
            data = await websocket.receive_json()
            chunk = runtime.streams.handle_event(data)
            if chunk and chunk.event_type == "start":
                active_sid = chunk.call_sid or active_sid
                active_shop = chunk.shop_id or active_shop
                active_to = chunk.to_number or active_to
            if chunk and chunk.event_type == "interrupt":
                call = await runtime.store.get_call_by_sid(
                    chunk.call_sid, shop_id=chunk.shop_id
                )
                if call is None:
                    call = await runtime.store.get_call_by_sid(chunk.call_sid)
                if call:
                    await runtime.memory.mark_interrupted(
                        shop_id=call.shop_id, call_id=call.id
                    )
            if chunk and chunk.event_type == "stop":
                active_sid = chunk.call_sid or active_sid
                active_shop = chunk.shop_id or active_shop
                active_to = chunk.to_number or active_to
                await _close_active("stop")
                break
    except WebSocketDisconnect:
        logger.info("voice.stream.disconnected sid=%s", active_sid)
        await _close_active("disconnect")
    except Exception:  # noqa: BLE001
        logger.exception("voice.stream.error sid=%s", active_sid)
        await _close_active("error")
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


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
