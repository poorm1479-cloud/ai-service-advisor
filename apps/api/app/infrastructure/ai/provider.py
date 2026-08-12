"""AI chat provider abstraction — OpenAI with Ollama local fallback.

Transport-only layer. Prompts and JSON decision parsing stay in callers.
Ollama uses the native /api/chat endpoint with think=false (Qwen3-safe).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.infrastructure.config import settings

logger = logging.getLogger(__name__)


class AIProviderError(Exception):
    """Raised when a chat provider fails in a fallback-eligible way."""


class AIProviderUnavailable(AIProviderError):
    """Provider cannot be used (missing key, unreachable, etc.)."""


@dataclass(slots=True)
class ChatCompletionResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""


class ChatProvider(Protocol):
    name: str

    def available(self) -> bool:
        """Return True when this provider can be attempted."""

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0,
        response_format: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> ChatCompletionResult:
        """Return assistant message content (and optional usage)."""


def _is_quota_error(status_code: int, body: str) -> bool:
    if status_code == 429:
        return True
    lowered = (body or "").lower()
    return any(
        token in lowered
        for token in (
            "insufficient_quota",
            "quota exceeded",
            "rate_limit",
            "rate limit",
        )
    )


def _raise_http_as_provider_error(exc: httpx.HTTPStatusError, *, provider: str) -> None:
    status = exc.response.status_code
    body = ""
    try:
        body = exc.response.text
    except Exception:
        body = ""
    if _is_quota_error(status, body):
        raise AIProviderError(f"{provider} quota/rate-limit error ({status})") from exc
    raise AIProviderError(f"{provider} API failure ({status})") from exc


class OpenAIChatProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._base_url = (base_url or settings.openai_base_url).rstrip("/")
        self._model = model or settings.openai_extraction_model

    def available(self) -> bool:
        from app.infrastructure.ai.openai_runtime import is_openai_enabled

        return is_openai_enabled() and bool((self._api_key or "").strip())

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0,
        response_format: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> ChatCompletionResult:
        from app.infrastructure.ai.openai_runtime import is_openai_enabled

        if not is_openai_enabled():
            raise AIProviderUnavailable("OpenAI usage is disabled by platform admin")
        if not self.available():
            raise AIProviderUnavailable("OPENAI_API_KEY is not set")

        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": temperature,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                response = await client.post("/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise AIProviderError("openai timeout") from exc
        except httpx.HTTPStatusError as exc:
            _raise_http_as_provider_error(exc, provider="openai")
        except httpx.RequestError as exc:
            raise AIProviderError(f"openai API failure: {exc}") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"openai invalid response: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AIProviderError("openai returned empty content")
        except (KeyError, TypeError, IndexError, AIProviderError) as exc:
            if isinstance(exc, AIProviderError):
                raise
            raise AIProviderError(f"openai invalid response: {exc}") from exc

        usage = body.get("usage") or {}
        return ChatCompletionResult(
            content=content,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            provider=self.name,
        )


def _ollama_native_base(url: str) -> str:
    """Normalize OLLAMA_URL to the native root (no /v1 suffix)."""
    base = (url or "").strip().rstrip("/")
    if not base:
        base = "http://localhost:11434"
    if base.endswith("/v1"):
        return base[: -len("/v1")] or "http://localhost:11434"
    return base


class OllamaChatProvider:
    """Ollama via native /api/chat.

    Uses the native endpoint (not OpenAI-compat /v1) so we can pass
    ``think: false`` — required for Qwen3 and other thinking models, which
    otherwise burn the whole timeout on hidden reasoning and return empty/late
    content over /v1/chat/completions.
    """

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = _ollama_native_base(base_url or settings.ollama_url)
        self._model = model or settings.ollama_model

    def available(self) -> bool:
        return bool((self._base_url or "").strip() and (self._model or "").strip())

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0,
        response_format: dict[str, str] | None = None,
        timeout: float = 90.0,
    ) -> ChatCompletionResult:
        if not self.available():
            raise AIProviderUnavailable("OLLAMA_URL / OLLAMA_MODEL not configured")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            # Disable thinking traces — critical for qwen3:* structured JSON.
            "think": False,
            "options": {"temperature": temperature},
        }
        if response_format is not None and response_format.get("type") == "json_object":
            payload["format"] = "json"

        headers = {"Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                response = await client.post("/api/chat", headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise AIProviderError("ollama timeout") from exc
        except httpx.HTTPStatusError as exc:
            _raise_http_as_provider_error(exc, provider="ollama")
        except httpx.RequestError as exc:
            raise AIProviderError(f"ollama API failure: {exc}") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"ollama invalid response: {exc}") from exc

        try:
            content = body["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AIProviderError("ollama returned empty content")
        except (KeyError, TypeError, AIProviderError) as exc:
            if isinstance(exc, AIProviderError):
                raise
            raise AIProviderError(f"ollama invalid response: {exc}") from exc

        return ChatCompletionResult(
            content=content,
            input_tokens=int(body.get("prompt_eval_count") or 0),
            output_tokens=int(body.get("eval_count") or 0),
            provider=self.name,
        )


class FallbackChatProvider:
    """Try primary (OpenAI); on key/quota/timeout/API failure use secondary (Ollama)."""

    name = "fallback"

    def __init__(self, primary: ChatProvider, secondary: ChatProvider) -> None:
        self._primary = primary
        self._secondary = secondary

    def available(self) -> bool:
        return self._primary.available() or self._secondary.available()

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0,
        response_format: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> ChatCompletionResult:
        primary_error: Exception | None = None
        if self._primary.available():
            try:
                return await self._primary.complete(
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                    timeout=timeout,
                )
            except AIProviderError as exc:
                primary_error = exc
                logger.warning(
                    "AI provider %s failed (%s); falling back to %s",
                    self._primary.name,
                    exc,
                    self._secondary.name,
                )
        else:
            primary_error = AIProviderUnavailable(f"{self._primary.name} unavailable")
            logger.info(
                "AI provider %s unavailable; using %s",
                self._primary.name,
                self._secondary.name,
            )

        try:
            return await self._secondary.complete(
                messages=messages,
                temperature=temperature,
                response_format=response_format,
                timeout=timeout,
            )
        except AIProviderError as exc:
            if primary_error is not None:
                raise AIProviderError(
                    f"primary ({self._primary.name}): {primary_error}; "
                    f"fallback ({self._secondary.name}): {exc}"
                ) from exc
            raise


def build_chat_provider(provider_name: str | None = None) -> ChatProvider:
    """Build chat provider from AI_PROVIDER (openai = OpenAI only; ollama = Ollama only)."""
    name = (provider_name or settings.ai_provider or "heuristic").strip().lower()
    if name == "ollama":
        return OllamaChatProvider()
    if name == "openai":
        return OpenAIChatProvider()
    raise ValueError(f"No chat provider for AI_PROVIDER={name!r}")
