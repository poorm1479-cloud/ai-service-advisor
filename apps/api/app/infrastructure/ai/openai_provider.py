from __future__ import annotations

import json

import httpx

from app.infrastructure.ai.ports import (
    RepairExtractionPort,
    RepairExtractionResult,
    SpeechSynthesisResult,
    SpeechToTextPort,
    TextToSpeechPort,
)
from app.infrastructure.ai.provider import (
    AIProviderError,
    AIProviderUnavailable,
    ChatProvider,
    OpenAIChatProvider,
)
from app.infrastructure.config import settings

REPAIR_EXTRACTION_SYSTEM = (
    "You extract structured auto-repair notes from mechanic speech. "
    "Return ONLY valid JSON with keys: service, condition, recommendation, mileage. "
    "mileage must be an integer or null. recommendation may be null."
)


def _coerce_json_object(raw: str) -> str:
    """Accept plain JSON or markdown-fenced JSON from local models."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _is_speech_quota_error(status_code: int, body: str) -> bool:
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



class OpenAISpeechToText(SpeechToTextPort):
    name = "openai_whisper"

    def available(self) -> bool:
        return bool((settings.openai_api_key or "").strip())

    async def transcribe(self, *, audio_bytes: bytes, filename: str, content_type: str | None) -> str:
        from app.saas.quota_context import consume_ai_quota_if_scoped

        await consume_ai_quota_if_scoped(1)
        if not self.available():
            raise AIProviderUnavailable("OPENAI_API_KEY is required for OpenAI speech-to-text")

        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        files = {
            "file": (filename or "audio.webm", audio_bytes, content_type or "application/octet-stream"),
            "model": (None, settings.openai_stt_model),
        }
        try:
            async with httpx.AsyncClient(base_url=settings.openai_base_url, timeout=120.0) as client:
                response = await client.post("/audio/transcriptions", headers=headers, files=files)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise AIProviderError("openai_whisper timeout") from exc
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text
            except Exception:
                body = ""
            if _is_speech_quota_error(exc.response.status_code, body):
                raise AIProviderError(
                    f"openai_whisper quota/rate-limit error ({exc.response.status_code})"
                ) from exc
            raise AIProviderError(
                f"openai_whisper API failure ({exc.response.status_code})"
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"openai_whisper API failure: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise AIProviderError(f"openai_whisper invalid response: {exc}") from exc

        text = str(data.get("text", "")).strip()
        if not text:
            raise AIProviderError("openai_whisper returned empty transcript")
        from app.saas.usage_tracking import record_ai_usage_if_scoped

        await record_ai_usage_if_scoped(operation="stt", requests=1)
        return text


class OpenAITextToSpeech(TextToSpeechPort):
    name = "openai_tts"

    def available(self) -> bool:
        return bool((settings.openai_api_key or "").strip())

    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        from app.saas.quota_context import consume_ai_quota_if_scoped

        await consume_ai_quota_if_scoped(1)
        if not self.available():
            raise AIProviderUnavailable("OPENAI_API_KEY is required for OpenAI text-to-speech")

        spoken = (text or "").strip()
        selected_voice = voice or settings.openai_tts_voice
        payload = {
            "model": settings.openai_tts_model,
            "input": spoken,
            "voice": selected_voice,
            "response_format": "mp3",
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(base_url=settings.openai_base_url, timeout=60.0) as client:
                response = await client.post("/audio/speech", headers=headers, json=payload)
                response.raise_for_status()
                audio = response.content
        except httpx.TimeoutException as exc:
            raise AIProviderError("openai_tts timeout") from exc
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text
            except Exception:
                body = ""
            if _is_speech_quota_error(exc.response.status_code, body):
                raise AIProviderError(
                    f"openai_tts quota/rate-limit error ({exc.response.status_code})"
                ) from exc
            raise AIProviderError(
                f"openai_tts API failure ({exc.response.status_code})"
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"openai_tts API failure: {exc}") from exc

        from app.saas.usage_tracking import record_ai_usage_if_scoped

        await record_ai_usage_if_scoped(
            operation="tts", requests=1, char_count=len(spoken)
        )
        return SpeechSynthesisResult(
            audio_bytes=audio,
            content_type="audio/mpeg",
            voice=selected_voice,
            text=spoken,
        )


class OpenAIRepairExtraction(RepairExtractionPort):
    """Repair extraction via chat provider (OpenAI, Ollama, or OpenAI→Ollama fallback)."""

    def __init__(self, chat: ChatProvider | None = None) -> None:
        self._chat = chat or OpenAIChatProvider()

    async def extract(self, *, transcript: str) -> RepairExtractionResult:
        from app.saas.quota_context import consume_ai_quota_if_scoped

        await consume_ai_quota_if_scoped(1)

        user = f"Transcript:\n{transcript}"
        result = await self._chat.complete(
            messages=[
                {"role": "system", "content": REPAIR_EXTRACTION_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=90.0,
        )
        data = json.loads(_coerce_json_object(result.content))

        from app.saas.usage_tracking import record_ai_usage_if_scoped

        await record_ai_usage_if_scoped(
            operation="extract",
            requests=1,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

        mileage_raw = data.get("mileage")
        mileage = int(mileage_raw) if mileage_raw is not None and str(mileage_raw).strip() != "" else None
        recommendation = data.get("recommendation")
        if recommendation is not None:
            recommendation = str(recommendation).strip() or None

        return RepairExtractionResult(
            service=str(data.get("service") or "General service").strip(),
            condition=str(data.get("condition") or transcript).strip(),
            recommendation=recommendation,
            mileage=mileage,
        )
