"""Speech adapters — STT / TTS (communication only)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from app.plugins.voice.metrics import VoiceMetricsCollector


class SpeechToTextPort(Protocol):
    async def transcribe(
        self,
        *,
        audio_bytes: bytes | None = None,
        text_hint: str | None = None,
        filename: str = "call.wav",
        content_type: str | None = None,
    ) -> str: ...


class TextToSpeechPort(Protocol):
    async def synthesize(
        self,
        *,
        text: str,
        voice: str = "alice",
    ) -> dict[str, Any]: ...


class FakeSpeechToText:
    """Deterministic STT for tests / local — no external network."""

    async def transcribe(
        self,
        *,
        audio_bytes: bytes | None = None,
        text_hint: str | None = None,
        filename: str = "call.wav",
        content_type: str | None = None,
    ) -> str:
        if text_hint:
            return text_hint.strip()
        if audio_bytes:
            # Decode trivial UTF-8 payloads used in tests; otherwise placeholder
            try:
                decoded = audio_bytes.decode("utf-8").strip()
                if decoded:
                    return decoded
            except UnicodeDecodeError:
                pass
            return f"[transcribed audio {len(audio_bytes)} bytes from {filename}]"
        return ""


class FakeTextToSpeech:
    async def synthesize(self, *, text: str, voice: str = "alice") -> dict[str, Any]:
        return {
            "text": text,
            "voice": voice,
            "audio_url": f"https://voice.local/tts/{uuid4().hex}.mp3",
            "provider": "fake",
            "duration_estimate_sec": max(1.0, len(text.split()) * 0.4),
        }


@dataclass
class SpeechService:
    """Voice plugin speech facade — never executes business actions."""

    stt: SpeechToTextPort
    tts: TextToSpeechPort
    metrics: VoiceMetricsCollector | None = None

    async def speech_to_text(self, **kwargs: Any) -> dict[str, Any]:
        started = time.perf_counter()
        text = await self.stt.transcribe(
            audio_bytes=kwargs.get("audio_bytes"),
            text_hint=kwargs.get("text") or kwargs.get("text_hint") or kwargs.get("speech_result"),
            filename=kwargs.get("filename") or "call.wav",
            content_type=kwargs.get("content_type"),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if self.metrics:
            self.metrics.record_response_time(elapsed_ms)
        return {
            "text": text,
            "latency_ms": round(elapsed_ms, 2),
            "business_actions_executed": False,
        }

    async def text_to_speech(self, *, text: str, voice: str = "alice", **_: Any) -> dict[str, Any]:
        started = time.perf_counter()
        result = await self.tts.synthesize(text=text, voice=voice)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if self.metrics:
            self.metrics.record_response_time(elapsed_ms)
        return {
            **result,
            "latency_ms": round(elapsed_ms, 2),
            "business_actions_executed": False,
        }


def build_default_speech(metrics: VoiceMetricsCollector | None = None) -> SpeechService:
    """Prefer infrastructure AI ports when available; fall back to fake."""
    try:
        from app.infrastructure.ai.factory import build_ai_services

        ai = build_ai_services()
        stt = getattr(ai, "stt", None) or getattr(ai, "speech_to_text", None) or FakeSpeechToText()
        tts = getattr(ai, "tts", None) or getattr(ai, "text_to_speech", None) or FakeTextToSpeech()

        class _SttAdapter:
            def __init__(self, port: Any) -> None:
                self._port = port

            async def transcribe(self, **kwargs: Any) -> str:
                if isinstance(self._port, FakeSpeechToText):
                    return await self._port.transcribe(**kwargs)
                hint = kwargs.get("text_hint")
                if hint:
                    return str(hint).strip()
                audio = kwargs.get("audio_bytes")
                if audio:
                    return await self._port.transcribe(
                        audio_bytes=audio,
                        filename=kwargs.get("filename") or "call.wav",
                        content_type=kwargs.get("content_type"),
                    )
                return ""

        class _TtsAdapter:
            def __init__(self, port: Any) -> None:
                self._port = port

            async def synthesize(self, *, text: str, voice: str = "alice") -> dict[str, Any]:
                if isinstance(self._port, FakeTextToSpeech):
                    return await self._port.synthesize(text=text, voice=voice)
                synth = await self._port.synthesize(text=text, voice=voice)
                audio_url = getattr(synth, "audio_url", None) or getattr(synth, "url", None)
                return {
                    "text": text,
                    "voice": voice,
                    "audio_url": audio_url or f"https://voice.local/tts/{uuid4().hex}.mp3",
                    "provider": type(self._port).__name__,
                    "raw": synth,
                }

        return SpeechService(stt=_SttAdapter(stt), tts=_TtsAdapter(tts), metrics=metrics)
    except Exception:  # noqa: BLE001
        return SpeechService(stt=FakeSpeechToText(), tts=FakeTextToSpeech(), metrics=metrics)
