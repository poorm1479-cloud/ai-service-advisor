from __future__ import annotations

import re

from app.infrastructure.ai.ports import (
    RepairExtractionPort,
    RepairExtractionResult,
    SpeechSynthesisResult,
    SpeechToTextPort,
    TextToSpeechPort,
)


class HeuristicSpeechToText(SpeechToTextPort):
    """Dev/test STT.

    - If the uploaded file is UTF-8 text (e.g. .txt), treat contents as transcript.
    - Otherwise return a representative sample transcript for local demos.
    """

    SAMPLE = (
        "2019 Honda Accord oil change completed. "
        "Brake pads are 30 percent. "
        "Recommend replacement next visit. "
        "Mileage 82000."
    )

    async def transcribe(self, *, audio_bytes: bytes, filename: str, content_type: str | None) -> str:
        lower = filename.lower()
        if lower.endswith(".txt") or (content_type or "").startswith("text/"):
            try:
                text = audio_bytes.decode("utf-8").strip()
                if text:
                    return text
            except UnicodeDecodeError:
                pass
        return self.SAMPLE


class HeuristicTextToSpeech(TextToSpeechPort):
    """Dev/test TTS — returns UTF-8 spoken text (Twilio <Say> uses text)."""

    async def synthesize(self, *, text: str, voice: str | None = None) -> SpeechSynthesisResult:
        spoken = (text or "").strip()
        return SpeechSynthesisResult(
            audio_bytes=spoken.encode("utf-8"),
            content_type="text/plain",
            voice=voice or "alice",
            text=spoken,
        )


class HeuristicRepairExtraction(RepairExtractionPort):
    """Rule-based extractor for demos/tests without an LLM API key."""

    async def extract(self, *, transcript: str) -> RepairExtractionResult:
        text = " ".join(transcript.strip().split())
        if not text:
            return RepairExtractionResult(
                service="Inspection",
                condition="No transcript content",
                recommendation=None,
                mileage=None,
            )

        mileage = None
        mileage_match = re.search(
            r"(?:mileage|odometer|miles?)\s*(?:is|=|:)?\s*([\d,]+)",
            text,
            flags=re.IGNORECASE,
        )
        if mileage_match:
            mileage = int(mileage_match.group(1).replace(",", ""))
        else:
            bare = re.search(r"\b(\d{4,6})\b(?:\s*(?:miles?|mi))?", text, flags=re.IGNORECASE)
            if bare:
                mileage = int(bare.group(1).replace(",", ""))

        recommendation = None
        rec_match = re.search(
            r"(?:recommend(?:ed|ation)?|suggest(?:ed)?)\s+(.+?)(?:\.|$)",
            text,
            flags=re.IGNORECASE,
        )
        if rec_match:
            recommendation = rec_match.group(1).strip(" .")

        service = "General service"
        service_patterns = [
            (r"oil\s*change", "Oil Change"),
            (r"brake\s*pad", "Brake Service"),
            (r"tire|rotation", "Tire Service"),
            (r"diagnostic|check\s*engine", "Diagnostics"),
            (r"inspection", "Inspection"),
        ]
        for pattern, label in service_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                service = label
                break

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        condition = sentences[0] if sentences else text
        for sentence in sentences:
            if re.search(r"percent|%|worn|completed|condition", sentence, flags=re.IGNORECASE):
                condition = sentence.rstrip(".")
                break

        return RepairExtractionResult(
            service=service,
            condition=condition,
            recommendation=recommendation,
            mileage=mileage,
        )
