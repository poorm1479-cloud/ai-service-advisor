"""Speech package."""

from app.plugins.voice.speech.service import (
    FakeSpeechToText,
    FakeTextToSpeech,
    SpeechService,
    build_default_speech,
)

__all__ = [
    "FakeSpeechToText",
    "FakeTextToSpeech",
    "SpeechService",
    "build_default_speech",
]
