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
    to_number: str | None = None
    chunks: int = 0
    interrupted: bool = False
    audio_buffer: bytearray = field(default_factory=bytearray)


class MediaStreamHub:
    """In-process hub for Twilio Media Stream websocket events."""

    def __init__(self, monitor: VoiceMonitor | None = None) -> None:
        self._sessions: dict[str, StreamSession] = {}
        self._by_call_sid: dict[str, str] = {}  # call_sid → stream_sid
        self._monitor = monitor or VoiceMonitor()

    @property
    def sessions(self) -> dict[str, StreamSession]:
        return self._sessions

    def get_session_by_call_sid(self, call_sid: str) -> StreamSession | None:
        stream_sid = self._by_call_sid.get(call_sid)
        if not stream_sid:
            return None
        return self._sessions.get(stream_sid)

    def handle_event(self, payload: dict[str, Any]) -> StreamChunk | None:
        event = str(payload.get("event") or "")
        self._monitor.record_stream_event()

        if event == "start":
            start = payload.get("start") or {}
            call_sid = str(start.get("callSid") or payload.get("callSid") or "")
            stream_sid = str(start.get("streamSid") or payload.get("streamSid") or "")
            session = StreamSession(call_sid=call_sid, stream_sid=stream_sid)
            custom = start.get("customParameters") or {}
            # Twilio may send parameter keys lowercased or as nested strings.
            shop_raw = custom.get("shop_id") or custom.get("ShopId") or custom.get("shopId")
            if shop_raw:
                try:
                    session.shop_id = UUID(str(shop_raw))
                except ValueError:
                    pass
            to_raw = custom.get("to_number") or custom.get("To") or custom.get("to")
            if to_raw:
                session.to_number = str(to_raw)
            self._sessions[stream_sid] = session
            if call_sid:
                self._by_call_sid[call_sid] = stream_sid
            logger.info(
                "voice.stream.start call=%s stream=%s shop=%s",
                call_sid,
                stream_sid,
                session.shop_id,
            )
            return StreamChunk(
                call_sid=call_sid,
                stream_sid=stream_sid,
                event_type="start",
                payload=payload,
                shop_id=session.shop_id,
                to_number=session.to_number,
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
                sequence_number=int(media["chunk"])
                if str(media.get("chunk", "")).isdigit()
                else None,
                shop_id=session.shop_id,
                to_number=session.to_number,
            )

        if event == "stop":
            stream_sid = str(payload.get("streamSid") or "")
            session = self._sessions.pop(stream_sid, None)
            if session is None:
                return None
            self._by_call_sid.pop(session.call_sid, None)
            logger.info(
                "voice.stream.stop call=%s chunks=%s bytes=%s shop=%s",
                session.call_sid,
                session.chunks,
                len(session.audio_buffer),
                session.shop_id,
            )
            return StreamChunk(
                call_sid=session.call_sid,
                stream_sid=stream_sid,
                event_type="stop",
                payload=payload,
                shop_id=session.shop_id,
                to_number=session.to_number,
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
                shop_id=session.shop_id if session else None,
                to_number=session.to_number if session else None,
            )

        return None
