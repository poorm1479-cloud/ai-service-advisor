"""OpenAI → Ollama chat provider fallback."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.infrastructure.ai.factory import build_ai_services
from app.infrastructure.ai.openai_provider import OpenAIRepairExtraction, REPAIR_EXTRACTION_SYSTEM
from app.infrastructure.ai.provider import (
    AIProviderError,
    AIProviderUnavailable,
    ChatCompletionResult,
    FallbackChatProvider,
    OllamaChatProvider,
    OpenAIChatProvider,
    build_chat_provider,
)
from app.infrastructure import config


class _FakeChat:
    name = "fake"

    def __init__(
        self,
        *,
        available: bool = True,
        result: ChatCompletionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._available = available
        self._result = result
        self._error = error
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def complete(self, **kwargs: Any) -> ChatCompletionResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.asyncio
async def test_fallback_uses_openai_when_available() -> None:
    primary = _FakeChat(
        result=ChatCompletionResult(content='{"ok":true}', provider="openai"),
    )
    secondary = _FakeChat(
        result=ChatCompletionResult(content='{"ok":false}', provider="ollama"),
    )
    fb = FallbackChatProvider(primary, secondary)
    out = await fb.complete(messages=[{"role": "user", "content": "hi"}])
    assert out.content == '{"ok":true}'
    assert primary.calls == 1
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_fallback_on_missing_api_key() -> None:
    primary = _FakeChat(available=False)
    secondary = _FakeChat(
        result=ChatCompletionResult(content='{"via":"ollama"}', provider="ollama"),
    )
    fb = FallbackChatProvider(primary, secondary)
    out = await fb.complete(messages=[{"role": "user", "content": "hi"}])
    assert out.provider == "ollama"
    assert primary.calls == 0
    assert secondary.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AIProviderError("openai quota/rate-limit error (429)"),
        AIProviderError("openai timeout"),
        AIProviderError("openai API failure (500)"),
        AIProviderUnavailable("OPENAI_API_KEY is not set"),
    ],
)
async def test_fallback_on_provider_errors(error: Exception) -> None:
    primary = _FakeChat(error=error)
    secondary = _FakeChat(
        result=ChatCompletionResult(content='{"via":"ollama"}', provider="ollama"),
    )
    fb = FallbackChatProvider(primary, secondary)
    out = await fb.complete(messages=[{"role": "user", "content": "hi"}])
    assert out.content == '{"via":"ollama"}'
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_fallback_raises_when_both_fail() -> None:
    primary = _FakeChat(error=AIProviderError("openai timeout"))
    secondary = _FakeChat(error=AIProviderError("ollama API failure"))
    fb = FallbackChatProvider(primary, secondary)
    with pytest.raises(AIProviderError, match="primary .* fallback"):
        await fb.complete(messages=[{"role": "user", "content": "hi"}])


def test_build_chat_provider_openai_is_fallback_chain() -> None:
    chat = build_chat_provider("openai")
    assert isinstance(chat, FallbackChatProvider)
    assert isinstance(chat._primary, OpenAIChatProvider)
    assert isinstance(chat._secondary, OllamaChatProvider)


def test_build_chat_provider_ollama_only() -> None:
    chat = build_chat_provider("ollama")
    assert isinstance(chat, OllamaChatProvider)


def test_ollama_native_base_strips_v1() -> None:
    from app.infrastructure.ai.provider import _ollama_native_base

    assert _ollama_native_base("http://localhost:11434") == "http://localhost:11434"
    assert _ollama_native_base("http://localhost:11434/") == "http://localhost:11434"
    assert _ollama_native_base("http://localhost:11434/v1") == "http://localhost:11434"
    assert _ollama_native_base("") == "http://localhost:11434"


@pytest.mark.asyncio
async def test_ollama_uses_native_chat_with_think_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "message": {"role": "assistant", "content": '{"ok":true}'},
                "prompt_eval_count": 3,
                "eval_count": 2,
            }

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["base_url"] = kwargs.get("base_url")
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, path: str, **kwargs: Any) -> _Response:
            captured["path"] = path
            captured["json"] = kwargs.get("json")
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    provider = OllamaChatProvider(
        base_url="http://localhost:11434/v1",
        model="qwen3:14b",
    )
    out = await provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    assert out.content == '{"ok":true}'
    assert out.provider == "ollama"
    assert captured["base_url"] == "http://localhost:11434"
    assert captured["path"] == "/api/chat"
    assert captured["json"]["think"] is False
    assert captured["json"]["stream"] is False
    assert captured["json"]["format"] == "json"
    assert captured["json"]["model"] == "qwen3:14b"


def test_factory_openai_wires_fallback_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "ai_provider", "openai")
    monkeypatch.setattr(config.settings, "openai_api_key", "sk-test")
    services = build_ai_services()
    assert isinstance(services.extractor, OpenAIRepairExtraction)
    assert isinstance(services.extractor._chat, FallbackChatProvider)


def test_factory_openai_wires_stt_tts_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.ai.openai_provider import OpenAISpeechToText, OpenAITextToSpeech
    from app.infrastructure.ai.speech_providers import (
        FallbackSpeechToText,
        FallbackTextToSpeech,
        LocalWhisperSpeechToText,
        PiperTextToSpeech,
    )

    monkeypatch.setattr(config.settings, "ai_provider", "openai")
    monkeypatch.setattr(config.settings, "openai_api_key", "sk-test")
    services = build_ai_services()
    assert isinstance(services.stt, FallbackSpeechToText)
    assert isinstance(services.stt._primary, OpenAISpeechToText)
    assert isinstance(services.stt._secondary, LocalWhisperSpeechToText)
    assert isinstance(services.tts, FallbackTextToSpeech)
    assert isinstance(services.tts._primary, OpenAITextToSpeech)
    assert isinstance(services.tts._secondary, PiperTextToSpeech)


def test_factory_ollama_wires_ollama_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "ai_provider", "ollama")
    services = build_ai_services()
    assert isinstance(services.extractor, OpenAIRepairExtraction)
    assert isinstance(services.extractor._chat, OllamaChatProvider)


@pytest.mark.asyncio
async def test_extraction_keeps_same_prompt_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class CapturingChat:
        name = "capture"

        def available(self) -> bool:
            return True

        async def complete(self, **kwargs: Any) -> ChatCompletionResult:
            captured.update(kwargs)
            return ChatCompletionResult(
                content=json.dumps(
                    {
                        "service": "Oil change",
                        "condition": "Dirty oil",
                        "recommendation": "Replace filter",
                        "mileage": 120000,
                    }
                ),
                input_tokens=10,
                output_tokens=20,
                provider="capture",
            )

    extractor = OpenAIRepairExtraction(chat=CapturingChat())
    result = await extractor.extract(transcript="oil looks dirty at 120k")

    assert captured["messages"][0]["content"] == REPAIR_EXTRACTION_SYSTEM
    assert captured["messages"][1]["content"] == "Transcript:\noil looks dirty at 120k"
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert result.service == "Oil change"
    assert result.condition == "Dirty oil"
    assert result.recommendation == "Replace filter"
    assert result.mileage == 120000


@pytest.mark.asyncio
async def test_openai_provider_unavailable_without_key() -> None:
    provider = OpenAIChatProvider(api_key="")
    assert provider.available() is False
    with pytest.raises(AIProviderUnavailable):
        await provider.complete(messages=[{"role": "user", "content": "x"}])


@pytest.mark.asyncio
async def test_openai_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIChatProvider(api_key="sk-test", base_url="http://example.invalid/v1")

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
        await provider.complete(messages=[{"role": "user", "content": "x"}])
