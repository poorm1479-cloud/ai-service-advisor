from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.api.schemas import RepairHistoryOut, VehicleOut
from app.application.voice_note_service import VoiceNoteService
from app.domain.exceptions import NotFoundError, ValidationError
from app.infrastructure.ai.factory import build_ai_services
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/v1/voice-notes", tags=["voice-notes"])


class ExtractionOut(BaseModel):
    service: str
    condition: str
    recommendation: str | None
    mileage: int | None


class VoiceNoteOut(BaseModel):
    id: UUID
    shop_id: UUID
    employee_id: UUID
    audio_url: str
    transcript: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VoiceNoteProcessOut(BaseModel):
    voice_note: VoiceNoteOut
    extraction: ExtractionOut
    repair_history: RepairHistoryOut
    vehicle: VehicleOut


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    raise exc


def _service(uow: SqlAlchemyUnitOfWork) -> VoiceNoteService:
    ai = build_ai_services()
    return VoiceNoteService(uow, stt=ai.stt, extractor=ai.extractor)


@router.post("", response_model=VoiceNoteProcessOut, status_code=status.HTTP_201_CREATED)
async def upload_and_process_voice_note(
    vehicle_id: UUID = Form(...),
    audio: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VoiceNoteProcessOut:
    data = await audio.read()
    service = _service(uow)
    from app.saas.quota_context import reset_quota_shop_id, set_quota_shop_id
    from app.saas.usage_tracking import reset_usage_shop_id, set_usage_shop_id

    token = set_quota_shop_id(current.shop_id)
    usage_token = set_usage_shop_id(current.shop_id)
    try:
        try:
            result = await service.process_upload(
                shop_id=current.shop_id,
                employee_id=current.user_id,
                vehicle_id=vehicle_id,
                audio_bytes=data,
                filename=audio.filename or "note.webm",
                content_type=audio.content_type,
            )
        except (ValidationError, NotFoundError) as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # AI provider failures
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI processing failed: {exc}",
            ) from exc
        return VoiceNoteProcessOut(
            voice_note=VoiceNoteOut.model_validate(result.voice_note),
            extraction=ExtractionOut(
                service=result.extraction.service,
                condition=result.extraction.condition,
                recommendation=result.extraction.recommendation,
                mileage=result.extraction.mileage,
            ),
            repair_history=RepairHistoryOut.model_validate(result.repair_history),
            vehicle=VehicleOut.model_validate(result.vehicle),
        )
    finally:
        reset_usage_shop_id(usage_token)
        reset_quota_shop_id(token)


@router.get("", response_model=list[VoiceNoteOut])
async def list_voice_notes(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[VoiceNoteOut]:
    service = _service(uow)
    notes = await service.list(shop_id=current.shop_id)
    return [VoiceNoteOut.model_validate(n) for n in notes]


@router.get("/{note_id}", response_model=VoiceNoteOut)
async def get_voice_note(
    note_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> VoiceNoteOut:
    service = _service(uow)
    try:
        note = await service.get(shop_id=current.shop_id, note_id=note_id)
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    return VoiceNoteOut.model_validate(note)


@router.get("/{note_id}/audio")
async def download_voice_note_audio(
    note_id: UUID,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> Response:
    service = _service(uow)
    try:
        note = await service.get(shop_id=current.shop_id, note_id=note_id)
        payload = service.read_audio(audio_url=note.audio_url)
    except NotFoundError as exc:
        raise _http_error(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Audio file missing") from exc

    media = "audio/webm"
    if note.audio_url.endswith(".wav"):
        media = "audio/wav"
    elif note.audio_url.endswith(".mp3"):
        media = "audio/mpeg"
    elif note.audio_url.endswith(".txt"):
        media = "text/plain"
    return Response(content=payload, media_type=media)
