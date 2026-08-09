from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.ai.heuristic import (
    HeuristicRepairExtraction,
    HeuristicSpeechToText,
    HeuristicTextToSpeech,
)
from app.infrastructure.ai.openai_provider import (
    OpenAIRepairExtraction,
    OpenAISpeechToText,
    OpenAITextToSpeech,
)
from app.infrastructure.ai.ports import RepairExtractionPort, SpeechToTextPort, TextToSpeechPort
from app.infrastructure.ai.provider import build_chat_provider
from app.infrastructure.ai.speech_providers import (
    FallbackSpeechToText,
    FallbackTextToSpeech,
    LocalWhisperSpeechToText,
    PiperTextToSpeech,
)
from app.infrastructure.config import settings


@dataclass(slots=True)
class AIServices:
    stt: SpeechToTextPort
    tts: TextToSpeechPort
    extractor: RepairExtractionPort


def build_ai_services() -> AIServices:
    provider = (settings.ai_provider or "heuristic").strip().lower()
    if provider == "openai":
        # AI chat/extraction: OpenAI → Ollama
        # STT: OpenAI Whisper → Local Whisper
        # TTS: OpenAI TTS → Piper
        return AIServices(
            stt=FallbackSpeechToText(OpenAISpeechToText(), LocalWhisperSpeechToText()),
            tts=FallbackTextToSpeech(OpenAITextToSpeech(), PiperTextToSpeech()),
            extractor=OpenAIRepairExtraction(chat=build_chat_provider("openai")),
        )
    if provider == "ollama":
        # Extraction/chat: Ollama
        # STT: Local Whisper → text-only path (.txt notes; never invents audio transcript)
        # TTS: Piper → heuristic text passthrough
        return AIServices(
            stt=FallbackSpeechToText(LocalWhisperSpeechToText(), HeuristicSpeechToText()),
            tts=FallbackTextToSpeech(PiperTextToSpeech(), HeuristicTextToSpeech()),
            extractor=OpenAIRepairExtraction(chat=build_chat_provider("ollama")),
        )
    return AIServices(
        stt=HeuristicSpeechToText(),
        tts=HeuristicTextToSpeech(),
        extractor=HeuristicRepairExtraction(),
    )

