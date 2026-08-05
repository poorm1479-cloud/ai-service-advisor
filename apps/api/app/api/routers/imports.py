"""Import Engine HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user
from app.import_engine.enums import ImportSource, MergeAction, SOURCE_PRIORITY
from app.import_engine.factory import ImportRuntime, get_import_runtime

router = APIRouter(prefix="/v1/imports", tags=["imports"])


def _runtime() -> ImportRuntime:
    return get_import_runtime()


class CreateImportRequest(BaseModel):
    source: ImportSource
    options: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)


class ManualSectionsRequest(BaseModel):
    sections: dict[str, list[dict[str, Any]]]


class RunImportRequest(BaseModel):
    auto_apply: bool = False


class DuplicateResolutionItem(BaseModel):
    duplicate_id: UUID
    action: MergeAction = MergeAction.MERGE


class ResolveDuplicatesRequest(BaseModel):
    resolutions: list[DuplicateResolutionItem]
    apply_after: bool = True


class ProgressOut(BaseModel):
    stage: str
    percent: int
    message: str
    processed: int = 0
    total: int = 0
    updated_at: datetime | None = None


class DuplicateOut(BaseModel):
    id: UUID
    entity_kind: str
    match_type: str
    confidence: float
    incoming_ref: str
    existing_ref: str | None
    incoming_snapshot: dict[str, Any]
    existing_snapshot: dict[str, Any]
    suggested_action: str
    resolved_action: str | None
    resolved: bool


class ValidationIssueOut(BaseModel):
    id: UUID
    severity: str
    code: str
    message: str
    entity_kind: str | None
    entity_ref: str | None
    details: dict[str, Any] = Field(default_factory=dict)


class EntityCountOut(BaseModel):
    imported: int = 0
    merged: int = 0
    skipped: int = 0
    failed: int = 0


class ReportOut(BaseModel):
    job_id: UUID
    source: str
    status: str
    entity_counts: dict[str, EntityCountOut]
    validation_issues: list[ValidationIssueOut]
    duplicates_resolved: int
    duplicates_pending: int
    duration_ms: int
    warnings: list[str]
    created_at: datetime | None
    completed_at: datetime | None


class ImportJobOut(BaseModel):
    id: UUID
    shop_id: UUID
    source: str
    status: str
    progress: ProgressOut
    filename: str | None
    batch_counts: dict[str, int] = Field(default_factory=dict)
    duplicates: list[DuplicateOut] = Field(default_factory=list)
    validation_issues: list[ValidationIssueOut] = Field(default_factory=list)
    report: ReportOut | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SourceInfo(BaseModel):
    source: str
    priority: int
    label: str
    requires_upload: bool
    requires_credentials: bool


def _job_out(job) -> ImportJobOut:
    report = None
    if job.report:
        report = ReportOut(
            job_id=job.report.job_id,
            source=job.report.source.value if hasattr(job.report.source, "value") else str(job.report.source),
            status=job.report.status.value if hasattr(job.report.status, "value") else str(job.report.status),
            entity_counts={
                k: EntityCountOut(
                    imported=v.imported,
                    merged=v.merged,
                    skipped=v.skipped,
                    failed=v.failed,
                )
                for k, v in job.report.entity_counts.items()
            },
            validation_issues=[
                ValidationIssueOut(
                    id=i.id,
                    severity=i.severity.value,
                    code=i.code,
                    message=i.message,
                    entity_kind=i.entity_kind.value if i.entity_kind else None,
                    entity_ref=i.entity_ref,
                    details=i.details,
                )
                for i in job.report.validation_issues
            ],
            duplicates_resolved=job.report.duplicates_resolved,
            duplicates_pending=job.report.duplicates_pending,
            duration_ms=job.report.duration_ms,
            warnings=job.report.warnings,
            created_at=job.report.created_at,
            completed_at=job.report.completed_at,
        )

    return ImportJobOut(
        id=job.id,
        shop_id=job.shop_id,
        source=job.source.value,
        status=job.status.value,
        progress=ProgressOut(
            stage=job.progress.stage.value if hasattr(job.progress.stage, "value") else str(job.progress.stage),
            percent=job.progress.percent,
            message=job.progress.message,
            processed=job.progress.processed,
            total=job.progress.total,
            updated_at=job.progress.updated_at,
        ),
        filename=job.filename,
        batch_counts=job.batch.counts() if job.batch else {},
        duplicates=[
            DuplicateOut(
                id=d.id,
                entity_kind=d.entity_kind.value,
                match_type=d.match_type.value,
                confidence=d.confidence,
                incoming_ref=d.incoming_ref,
                existing_ref=d.existing_ref,
                incoming_snapshot=d.incoming_snapshot,
                existing_snapshot=d.existing_snapshot,
                suggested_action=d.suggested_action.value,
                resolved_action=d.resolved_action.value if d.resolved_action else None,
                resolved=d.resolved,
            )
            for d in job.duplicates
        ],
        validation_issues=[
            ValidationIssueOut(
                id=i.id,
                severity=i.severity.value,
                code=i.code,
                message=i.message,
                entity_kind=i.entity_kind.value if i.entity_kind else None,
                entity_ref=i.entity_ref,
                details=i.details,
            )
            for i in job.validation_issues
        ],
        report=report,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/sources", response_model=list[SourceInfo])
async def list_sources(_: CurrentUser = Depends(get_current_user)) -> list[SourceInfo]:
    labels = {
        ImportSource.TEKMETRIC: "Tekmetric API",
        ImportSource.SHOPMONKEY: "Shopmonkey API",
        ImportSource.AUTOLEAP: "AutoLeap API",
        ImportSource.MITCHELL: "Mitchell API",
        ImportSource.CSV: "CSV",
        ImportSource.EXCEL: "Excel",
        ImportSource.PDF: "PDF",
        ImportSource.OCR: "OCR",
        ImportSource.MANUAL: "Manual Entry",
    }
    upload = {ImportSource.CSV, ImportSource.EXCEL, ImportSource.PDF, ImportSource.OCR}
    creds = {
        ImportSource.TEKMETRIC,
        ImportSource.SHOPMONKEY,
        ImportSource.AUTOLEAP,
        ImportSource.MITCHELL,
    }
    return [
        SourceInfo(
            source=s.value,
            priority=SOURCE_PRIORITY[s],
            label=labels[s],
            requires_upload=s in upload,
            requires_credentials=s in creds,
        )
        for s in sorted(ImportSource, key=lambda x: SOURCE_PRIORITY[x])
    ]


@router.post("", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
async def create_import_job(
    body: CreateImportRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    job = await rt.service.create_job(
        shop_id=user.shop_id,
        source=body.source,
        options=body.options,
        credentials=body.credentials,
    )
    rt.monitor.record_created(body.source.value)
    return _job_out(job)


@router.get("", response_model=list[ImportJobOut])
async def list_import_jobs(
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> list[ImportJobOut]:
    jobs = await rt.service.list_jobs(user.shop_id, limit=limit)
    return [_job_out(j) for j in jobs]


@router.get("/metrics/summary")
async def import_metrics(
    _: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> dict[str, Any]:
    return rt.monitor.snapshot()


@router.get("/{job_id}", response_model=ImportJobOut)
async def get_import_job(
    job_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    try:
        job = await rt.service.get_job(user.shop_id, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _job_out(job)


@router.post("/{job_id}/upload", response_model=ImportJobOut)
async def upload_import_file(
    job_id: UUID,
    file: UploadFile = File(...),
    ocr_text: str | None = Form(None),
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    payload = await file.read()
    try:
        job = await rt.service.attach_upload(
            shop_id=user.shop_id,
            job_id=job_id,
            payload=payload,
            filename=file.filename,
            content_type=file.content_type,
        )
        if ocr_text:
            job.options = {**job.options, "ocr_text": ocr_text}
            await rt.store.save_job(job)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _job_out(job)


@router.post("/{job_id}/manual", response_model=ImportJobOut)
async def set_manual_sections(
    job_id: UUID,
    body: ManualSectionsRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    try:
        job = await rt.service.set_manual_sections(
            shop_id=user.shop_id, job_id=job_id, sections=body.sections
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _job_out(job)


@router.post("/{job_id}/run", response_model=ImportJobOut)
async def run_import_job(
    job_id: UUID,
    body: RunImportRequest | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    auto_apply = body.auto_apply if body else False
    try:
        job = await rt.service.run(shop_id=user.shop_id, job_id=job_id, auto_apply=auto_apply)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job.status.value == "completed" and job.report:
        total = sum(c.imported for c in job.report.entity_counts.values())
        rt.monitor.record_completed(records=total, duplicates=len(job.duplicates))
    elif job.status.value == "failed":
        rt.monitor.record_failed()
    return _job_out(job)


@router.post("/{job_id}/duplicates/resolve", response_model=ImportJobOut)
async def resolve_duplicates(
    job_id: UUID,
    body: ResolveDuplicatesRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ImportJobOut:
    try:
        job = await rt.service.resolve_duplicates(
            shop_id=user.shop_id,
            job_id=job_id,
            resolutions=[r.model_dump() for r in body.resolutions],
            apply_after=body.apply_after,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job.status.value == "completed" and job.report:
        total = sum(c.imported for c in job.report.entity_counts.values())
        rt.monitor.record_completed(records=total, duplicates=len(job.duplicates))
    return _job_out(job)


@router.get("/{job_id}/report", response_model=ReportOut)
async def get_import_report(
    job_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: ImportRuntime = Depends(_runtime),
) -> ReportOut:
    try:
        job = await rt.service.get_job(user.shop_id, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out = _job_out(job)
    if out.report is None:
        raise HTTPException(status_code=404, detail="Report not available yet")
    return out.report
