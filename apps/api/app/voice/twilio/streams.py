"""Twilio Media Streams event handling (streaming support)."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.voice.models import StreamChunk
from app.voice.monitoring import VoiceMonitor

logger = logging.getLogger("asa.voice.streams")


@dataclass
class StreamSession:
    call_sid: str
    stream_sid: str
    shop_id: UUID | None = None
    call_id: UUID | None = None
    chunks: int = 0
    interrupted: bool = False
    audio_buffer: bytearray = field(default_factory=bytearray)


class MediaStreamHub:
    """In-process hub for Twilio Media Stream websocket events."""

    def __init__(self, monitor: VoiceMonitor | None = None) -> None:
        self._sessions: dict[str, StreamSession] = {}
        self._monitor = monitor or VoiceMonitor()

    @property
    def sessions(self) -> dict[str, StreamSession]:
        return self._sessions

    def handle_event(self, payload: dict[str, Any]) -> StreamChunk | None:
        event = str(payload.get("event") or "")
        self._monitor.record_stream_event()

        if event == "start":
            start = payload.get("start") or {}
            call_sid = str(start.get("callSid") or payload.get("callSid") or "")
            stream_sid = str(start.get("streamSid") or payload.get("streamSid") or "")
            session = StreamSession(call_sid=call_sid, stream_sid=stream_sid)
            custom = start.get("customParameters") or {}
            if custom.get("shop_id"):
                try:
                    session.shop_id = UUID(str(custom["shop_id"]))
                except ValueError:
                    pass
            self._sessions[stream_sid] = session
            logger.info("voice.stream.start call=%s stream=%s", call_sid, stream_sid)
            return StreamChunk(
                call_sid=call_sid,
                stream_sid=stream_sid,
                event_type="start",
                payload=payload,
            )

        if event == "media":
            media = payload.get("media") or {}
            stream_sid = str(payload.get("streamSid") or "")
            session = self._sessions.get(stream_sid)
            if session is None:
                return None
            session.chunks += 1
            payload_b64 = media.get("payload")
            if isinstance(payload_b64, str):
                try:
                    session.audio_buffer.extend(base64.b64decode(payload_b64))
                except Exception:  # noqa: BLE001
                    pass
            return StreamChunk(
                call_sid=session.call_sid,
                stream_sid=stream_sid,
                event_type="media",
                payload=payload,
                sequence_number=int(media["chunk"]) if str(media.get("chunk", "")).isdigit() else None,
            )

        if event == "stop":
            stream_sid = str(payload.get("streamSid") or "")
            session = self._sessions.pop(stream_sid, None)
            if session is None:
                return None
            logger.info(
                "voice.stream.stop call=%s chunks=%s bytes=%s",
                session.call_sid,
                session.chunks,
                len(session.audio_buffer),
            )
            return StreamChunk(
                call_sid=session.call_sid,
                stream_sid=stream_sid,
                event_type="stop",
                payload=payload,
            )

        if event in {"mark", "interrupt"}:
            stream_sid = str(payload.get("streamSid") or "")
            session = self._sessions.get(stream_sid)
            if session and event == "interrupt":
                session.interrupted = True
                self._monitor.record_interrupt()
            return StreamChunk(
                call_sid=session.call_sid if session else "",
                stream_sid=stream_sid,
                event_type=event,
                payload=payload,
            )

        return None
