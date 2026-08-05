"""STT/TTS provider fallbacks — Whisper→Local Whisper, OpenAI TTS→Piper."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.infrastructure.ai.ports import SpeechSynthesisResult
from app.infrastructure.ai.provider import AIProviderError, AIProviderUnavailable
from app.infrastructure.ai.speech_providers import (
    FallbackSpeechToText,
    FallbackTextToSpeech,
    LocalWhisperSpeechToText,
    PiperTextToSpeech,
)


class _FakeSTT:
    name = "fake_stt"

    def __init__(
        self,
        *,
        available: bool = True,
        text: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self._available = available
        self._text = text
        self._error = error
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def transcribe(
        self, *, audio_bytes: bytes, filename: str, content_type: str | None
    ) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._text is not None
        return self._text


class _FakeTTS:
    name = "fake_tts"

    def __init__(
        self,
        *,
        available: bool = True,
        result: SpeechSynthesisResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._available = available
        self._result = result
        self._error = error
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.asyncio
async def test_stt_fallback_uses_primary_when_available() -> None:
    primary = _FakeSTT(text="hello from whisper")
    secondary = _FakeSTT(text="hello from local")
    fb = FallbackSpeechToText(primary, secondary)
    out = await fb.transcribe(audio_bytes=b"x", filename="a.wav", content_type="audio/wav")
    assert out == "hello from whisper"
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_stt_fallback_on_missing_key() -> None:
    primary = _FakeSTT(available=False)
    secondary = _FakeSTT(text="via local whisper")
    fb = FallbackSpeechToText(primary, secondary)
    out = await fb.transcribe(audio_bytes=b"x", filename="a.wav", content_type=None)
    assert out == "via local whisper"
    assert primary.calls == 0
    assert secondary.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AIProviderError("openai_whisper quota/rate-limit error (429)"),
        AIProviderError("openai_whisper timeout"),
        AIProviderUnavailable("OPENAI_API_KEY is required for OpenAI speech-to-text"),
    ],
)
async def test_stt_fallback_on_provider_errors(error: Exception) -> None:
    primary = _FakeSTT(error=error)
    secondary = _FakeSTT(text="via local whisper")
    fb = FallbackSpeechToText(primary, secondary)
    out = await fb.transcribe(audio_bytes=b"x", filename="a.wav", content_type=None)
    assert out == "via local whisper"
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_stt_fallback_raises_when_both_fail() -> None:
    primary = _FakeSTT(error=AIProviderError("openai timeout"))
    secondary = _FakeSTT(error=AIProviderError("local_whisper API failure"))
    fb = FallbackSpeechToText(primary, secondary)
    with pytest.raises(AIProviderError, match="primary .* fallback"):
        await fb.transcribe(audio_bytes=b"x", filename="a.wav", content_type=None)


@pytest.mark.asyncio
async def test_tts_fallback_uses_primary_when_available() -> None:
    primary = _FakeTTS(
        result=SpeechSynthesisResult(
            audio_bytes=b"mp3", content_type="audio/mpeg", voice="alloy", text="hi"
        )
    )
    secondary = _FakeTTS(
        result=SpeechSynthesisResult(
            audio_bytes=b"wav", content_type="audio/wav", voice="piper", text="hi"
        )
    )
    fb = FallbackTextToSpeech(primary, secondary)
    out = await fb.synthesize(text="hi")
    assert out.audio_bytes == b"mp3"
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_tts_fallback_to_piper() -> None:
    primary = _FakeTTS(available=False)
    secondary = _FakeTTS(
        result=SpeechSynthesisResult(
            audio_bytes=b"wav", content_type="audio/wav", voice="piper", text="hi"
        )
    )
    fb = FallbackTextToSpeech(primary, secondary)
    out = await fb.synthesize(text="hi")
    assert out.content_type == "audio/wav"
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_local_whisper_unavailable_without_url() -> None:
    provider = LocalWhisperSpeechToText(base_url="", model="whisper-1")
    assert provider.available() is False
    with pytest.raises(AIProviderUnavailable):
        await provider.transcribe(audio_bytes=b"x", filename="a.wav", content_type=None)


@pytest.mark.asyncio
async def test_piper_unavailable_without_url() -> None:
    provider = PiperTextToSpeech(base_url="")
    assert provider.available() is False
    with pytest.raises(AIProviderUnavailable):
        await provider.synthesize(text="hi")


@pytest.mark.asyncio
async def test_local_whisper_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = LocalWhisperSpeechToText(base_url="http://example.invalid/v1")

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(AIProviderError, match="timeout"):
        await provider.transcribe(audio_bytes=b"x", filename="a.wav", content_type=None)


@pytest.mark.asyncio
async def test_piper_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = PiperTextToSpeech(base_url="http://example.invalid")

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(AIProviderError, match="timeout"):
        await provider.synthesize(text="hi")

