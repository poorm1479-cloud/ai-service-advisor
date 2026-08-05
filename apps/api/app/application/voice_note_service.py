from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.entities import RepairHistory, Vehicle, VoiceNote
from app.domain.exceptions import NotFoundError, ValidationError
from app.domain.repositories import UnitOfWork
from app.infrastructure.ai.ports import RepairExtractionPort, RepairExtractionResult, SpeechToTextPort
from app.infrastructure.config import settings
from app.infrastructure.storage.audio_storage import LocalAudioStorage


@dataclass(slots=True)
class VoiceNoteProcessResult:
    voice_note: VoiceNote
    extraction: RepairExtractionResult
    repair_history: RepairHistory
    vehicle: Vehicle


class VoiceNoteService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        stt: SpeechToTextPort,
        extractor: RepairExtractionPort,
        storage: LocalAudioStorage | None = None,
    ) -> None:
        self._uow = uow
        self._stt = stt
        self._extractor = extractor
        self._storage = storage or LocalAudioStorage()

    async def process_upload(
        self,
        *,
        shop_id: UUID,
        employee_id: UUID,
        vehicle_id: UUID,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
    ) -> VoiceNoteProcessResult:
        await self._uow.bind_shop(shop_id)

        max_bytes = settings.max_audio_upload_mb * 1024 * 1024
        if not audio_bytes:
            raise ValidationError("Audio file is empty")
        if len(audio_bytes) > max_bytes:
            raise ValidationError(f"Audio file exceeds {settings.max_audio_upload_mb}MB limit")

        vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle_id)
        if vehicle is None:
            raise NotFoundError("Vehicle not found")

        audio_url = self._storage.save(
            shop_id=shop_id,
            original_filename=filename or "note.webm",
            data=audio_bytes,
        )

        note = await self._uow.voice_notes.add(
            VoiceNote(
                id=uuid4(),
                shop_id=shop_id,
                employee_id=employee_id,
                audio_url=audio_url,
                transcript=None,
            )
        )

        transcript = await self._stt.transcribe(
            audio_bytes=audio_bytes,
            filename=filename or "note.webm",
            content_type=content_type,
        )
        if not transcript.strip():
            raise ValidationError("Speech-to-text returned an empty transcript")

        note = await self._uow.voice_notes.update(
            VoiceNote(
                id=note.id,
                shop_id=note.shop_id,
                employee_id=note.employee_id,
                audio_url=note.audio_url,
                transcript=transcript.strip(),
                created_at=note.created_at,
            )
        )

        extraction = await self._extractor.extract(transcript=transcript)
        description = extraction.condition
        if extraction.mileage is not None:
            description = f"{description} (reported mileage: {extraction.mileage})"

        repair = await self._uow.repair_histories.add(
            RepairHistory(
                id=uuid4(),
                shop_id=shop_id,
                customer_id=vehicle.customer_id,
                vehicle_id=vehicle.id,
                service_type=extraction.service[:100],
                description=description,
                cost=Decimal("0.00"),
                recommendation=extraction.recommendation,
            )
        )

        if extraction.mileage is not None and extraction.mileage != vehicle.mileage:
            vehicle = await self._uow.vehicles.update(
                Vehicle(
                    id=vehicle.id,
                    shop_id=vehicle.shop_id,
                    customer_id=vehicle.customer_id,
                    vin=vehicle.vin,
                    license_plate=vehicle.license_plate,
                    year=vehicle.year,
                    make=vehicle.make,
                    model=vehicle.model,
                    mileage=extraction.mileage,
                    created_at=vehicle.created_at,
                )
            )

        await self._uow.commit()
        await self._uow.bind_shop(shop_id)
        refreshed_note = await self._uow.voice_notes.get_by_id(shop_id, note.id)
        refreshed_vehicle = await self._uow.vehicles.get_by_id(shop_id, vehicle.id)
        if refreshed_note is None or refreshed_vehicle is None:
            raise NotFoundError("Voice note or vehicle not found after processing")

        return VoiceNoteProcessResult(
            voice_note=refreshed_note,
            extraction=extraction,
            repair_history=repair,
            vehicle=refreshed_vehicle,
        )

    async def list(self, *, shop_id: UUID) -> list[VoiceNote]:
        await self._uow.bind_shop(shop_id)
        return await self._uow.voice_notes.list_by_shop(shop_id)

    async def get(self, *, shop_id: UUID, note_id: UUID) -> VoiceNote:
        await self._uow.bind_shop(shop_id)
        note = await self._uow.voice_notes.get_by_id(shop_id, note_id)
        if note is None:
            raise NotFoundError("Voice note not found")
        return note

    def read_audio(self, *, audio_url: str) -> bytes:
        return self._storage.read(audio_url)
