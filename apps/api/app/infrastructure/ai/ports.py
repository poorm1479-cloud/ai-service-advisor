"""AI ports — swap implementations without changing application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class RepairExtractionResult:
    service: str
    condition: str
    recommendation: str | None
    mileage: int | None


@dataclass(slots=True)
class SpeechSynthesisResult:
    audio_bytes: bytes
    content_type: str
    voice: str
    text: str


class SpeechToTextPort(Protocol):
    async def transcribe(self, *, audio_bytes: bytes, filename: str, content_type: str | None) -> str:
        """Convert speech audio to plain text."""


class TextToSpeechPort(Protocol):
    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        """Convert text to spoken audio (or spoken-text payload for Twilio Say)."""


class RepairExtractionPort(Protocol):
    async def extract(self, *, transcript: str) -> RepairExtractionResult:
        """Extract structured repair fields from a mechanic transcript."""
