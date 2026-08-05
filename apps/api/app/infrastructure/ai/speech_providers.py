"""STT/TTS provider abstraction — OpenAI with local fallbacks.

Transport-only. Callers keep existing SpeechToTextPort / TextToSpeechPort usage.
Fallback chains:
  STT: OpenAI Whisper -> Local Whisper
  TTS: OpenAI TTS -> Piper
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.infrastructure.ai.ports import SpeechSynthesisResult, SpeechToTextPort, TextToSpeechPort
from app.infrastructure.ai.provider import AIProviderError, AIProviderUnavailable
from app.infrastructure.config import settings

logger = logging.getLogger(__name__)


class SpeechProvider(Protocol):
    name: str

    def available(self) -> bool: ...


class FallbackSpeechToText:
    """Try primary STT; on key/quota/timeout/API failure use secondary."""

    name = "fallback_stt"

    def __init__(self, primary: SpeechToTextPort, secondary: SpeechToTextPort) -> None:
        self._primary = primary
        self._secondary = secondary

    def available(self) -> bool:
        return _speech_available(self._primary) or _speech_available(self._secondary)

    async def transcribe(
        self, *, audio_bytes: bytes, filename: str, content_type: str | None
    ) -> str:
        primary_error: Exception | None = None
        if _speech_available(self._primary):
            try:
                return await self._primary.transcribe(
                    audio_bytes=audio_bytes, filename=filename, content_type=content_type
                )
            except AIProviderError as exc:
                primary_error = exc
                logger.warning(
                    "STT provider %s failed (%s); falling back to %s",
                    _speech_name(self._primary),
                    exc,
                    _speech_name(self._secondary),
                )
        else:
            primary_error = AIProviderUnavailable(
                f"{_speech_name(self._primary)} unavailable"
            )
            logger.info(
                "STT provider %s unavailable; using %s",
                _speech_name(self._primary),
                _speech_name(self._secondary),
            )

        try:
            return await self._secondary.transcribe(
                audio_bytes=audio_bytes, filename=filename, content_type=content_type
            )
        except AIProviderError as exc:
            if primary_error is not None:
                raise AIProviderError(
                    f"primary ({_speech_name(self._primary)}): {primary_error}; "
                    f"fallback ({_speech_name(self._secondary)}): {exc}"
                ) from exc
            raise


class FallbackTextToSpeech:
    """Try primary TTS; on key/quota/timeout/API failure use secondary."""

    name = "fallback_tts"

    def __init__(self, primary: TextToSpeechPort, secondary: TextToSpeechPort) -> None:
        self._primary = primary
        self._secondary = secondary

    def available(self) -> bool:
        return _speech_available(self._primary) or _speech_available(self._secondary)

    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        primary_error: Exception | None = None
        if _speech_available(self._primary):
            try:
                return await self._primary.synthesize(text=text, voice=voice)
            except AIProviderError as exc:
                primary_error = exc
                logger.warning(
                    "TTS provider %s failed (%s); falling back to %s",
                    _speech_name(self._primary),
                    exc,
                    _speech_name(self._secondary),
                )
        else:
            primary_error = AIProviderUnavailable(
                f"{_speech_name(self._primary)} unavailable"
            )
            logger.info(
                "TTS provider %s unavailable; using %s",
                _speech_name(self._primary),
                _speech_name(self._secondary),
            )

        try:
            return await self._secondary.synthesize(text=text, voice=voice)
        except AIProviderError as exc:
            if primary_error is not None:
                raise AIProviderError(
                    f"primary ({_speech_name(self._primary)}): {primary_error}; "
                    f"fallback ({_speech_name(self._secondary)}): {exc}"
                ) from exc
            raise


class LocalWhisperSpeechToText:
    """Local Whisper via OpenAI-compatible /audio/transcriptions endpoint."""

    name = "local_whisper"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        raw_url = settings.local_whisper_url if base_url is None else base_url
        self._base_url = (raw_url or "").rstrip("/")
        self._model = settings.local_whisper_model if model is None else model

    def available(self) -> bool:
        return bool((self._base_url or "").strip() and (self._model or "").strip())

    async def transcribe(
        self, *, audio_bytes: bytes, filename: str, content_type: str | None
    ) -> str:
        if not self.available():
            raise AIProviderUnavailable("LOCAL_WHISPER_URL / LOCAL_WHISPER_MODEL not configured")

        files = {
            "file": (
                filename or "audio.webm",
                audio_bytes,
                content_type or "application/octet-stream",
            ),
            "model": (None, self._model),
        }
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=120.0) as client:
                response = await client.post("/audio/transcriptions", files=files)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise AIProviderError("local_whisper timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(
                f"local_whisper API failure ({exc.response.status_code})"
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"local_whisper API failure: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise AIProviderError(f"local_whisper invalid response: {exc}") from exc

        text = str(data.get("text", "")).strip()
        if not text:
            raise AIProviderError("local_whisper returned empty transcript")
        return text


class PiperTextToSpeech:
    """Local Piper TTS HTTP server (POST JSON {text, voice} -> audio/wav)."""

    name = "piper"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        voice: str | None = None,
    ) -> None:
        raw_url = settings.piper_url if base_url is None else base_url
        self._base_url = (raw_url or "").rstrip("/")
        self._voice = settings.piper_voice if voice is None else voice

    def available(self) -> bool:
        return bool((self._base_url or "").strip())

    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        if not self.available():
            raise AIProviderUnavailable("PIPER_URL is not configured")

        spoken = (text or "").strip()
        selected_voice = voice or self._voice
        payload = {"text": spoken, "voice": selected_voice}
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=60.0) as client:
                response = await client.post("/", json=payload)
                response.raise_for_status()
                audio = response.content
                content_type = response.headers.get("content-type") or "audio/wav"
        except httpx.TimeoutException as exc:
            raise AIProviderError("piper timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(f"piper API failure ({exc.response.status_code})") from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"piper API failure: {exc}") from exc

        if not audio:
            raise AIProviderError("piper returned empty audio")

        return SpeechSynthesisResult(
            audio_bytes=audio,
            content_type=content_type.split(";")[0].strip(),
            voice=selected_voice,
            text=spoken,
        )


def _speech_available(provider: object) -> bool:
    available = getattr(provider, "available", None)
    if callable(available):
        return bool(available())
    return True


def _speech_name(provider: object) -> str:
    return str(getattr(provider, "name", None) or type(provider).__name__)
