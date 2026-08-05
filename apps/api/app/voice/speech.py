"""Voice speech pipeline — STT / TTS / interrupt handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.infrastructure.ai.ports import (
    RepairExtractionPort,
    RepairExtractionResult,
    SpeechSynthesisResult,
    SpeechToTextPort,
    TextToSpeechPort,
)

logger = logging.getLogger("asa.voice.speech")


@dataclass(slots=True)
class SpokenReply:
    text: str
    synthesis: SpeechSynthesisResult
    barge_in: bool = True


class SpeechPipeline:
    """Coordinates STT → (agent) → TTS with interruptible playback metadata."""

    def __init__(
        self,
        *,
        stt: SpeechToTextPort,
        tts: TextToSpeechPort,
        extractor: RepairExtractionPort,
        default_voice: str = "alice",
        barge_in: bool = True,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._extractor = extractor
        self._default_voice = default_voice
        self._barge_in = barge_in

    async def transcribe_audio(
        self, *, audio_bytes: bytes, filename: str = "call.wav", content_type: str | None = None
    ) -> str:
        text = await self._stt.transcribe(
            audio_bytes=audio_bytes, filename=filename, content_type=content_type
        )
        logger.info("voice.stt chars=%s", len(text))
        return text.strip()

    async def speak(self, *, text: str, voice: str | None = None) -> SpokenReply:
        synthesis = await self._tts.synthesize(text=text, voice=voice or self._default_voice)
        return SpokenReply(text=text, synthesis=synthesis, barge_in=self._barge_in)

    async def extract_repair_notes(self, *, transcript: str) -> RepairExtractionResult:
        return await self._extractor.extract(transcript=transcript)
