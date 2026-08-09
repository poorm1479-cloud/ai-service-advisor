"""SQLAlchemy import store (survives API restarts)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.import_engine.enums import (
    DuplicateMatchType,
    EntityKind,
    ImportJobStatus,
    ImportSource,
    MergeAction,
    ValidationSeverity,
)
from app.import_engine.models import (
    CanonicalAppointment,
    CanonicalCommunication,
    CanonicalCustomer,
    CanonicalEstimate,
    CanonicalInvoice,
    CanonicalRecommendation,
    CanonicalRepairHistory,
    CanonicalVehicle,
    DuplicateCandidate,
    EntityCountSummary,
    ImportedRecord,
    ImportJob,
    ImportProgress,
    ImportReport,
    NormalizedBatch,
    ValidationIssue,
)
from app.infrastructure.models import ImportDuplicateModel, ImportJobModel, ImportRecordModel

logger = logging.getLogger("asa.import.sql_store")

_ENGINE_KEY = "__engine__"


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "value"):
        try:
            return obj.value
        except Exception:  # noqa: BLE001
            pass
    return obj


def _dumps(obj: Any) -> str:
    return json.dumps(_jsonable(obj), separators=(",", ":"), default=str)


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _enum(enum_cls: type, value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _customer_from_dict(d: dict[str, Any]) -> CanonicalCustomer:
    return CanonicalCustomer(
        external_id=d.get("external_id"),
        name=str(d.get("name") or ""),
        phone=d.get("phone"),
        email=d.get("email"),
        address=d.get("address"),
        source=_enum(ImportSource, d.get("source"), ImportSource.MANUAL),
        metadata=dict(d.get("metadata") or {}),
        row_ref=d.get("row_ref"),
    )


def _vehicle_from_dict(d: dict[str, Any]) -> CanonicalVehicle:
    return CanonicalVehicle(
        external_id=d.get("external_id"),
        vin=str(d.get("vin") or ""),
        year=d.get("year"),
        make=d.get("make"),
        model=d.get("model"),
        mileage=d.get("mileage"),
        license_plate=d.get("license_plate"),
        customer_external_id=d.get("customer_external_id"),
        customer_phone=d.get("customer_phone"),
        customer_name=d.get("customer_name"),
        source=_enum(ImportSource, d.get("source"), ImportSource.MANUAL),
        metadata=dict(d.get("metadata") or {}),
        row_ref=d.get("row_ref"),
    )


def _repair_from_dict(d: dict[str, Any]) -> CanonicalRepairHistory:
    cost = d.get("cost") or "0"
    return CanonicalRepairHistory(
        external_id=d.get("external_id"),
        vehicle_vin=d.get("vehicle_vin"),
        vehicle_external_id=d.get("vehicle_external_id"),
        customer_external_id=d.get("customer_external_id"),
        service_type=str(d.get("service_type") or "general"),
        description=str(d.get("description") or ""),
        cost=Decimal(str(cost)),
        recommendation=d.get("recommendation"),
        mileage_at_service=d.get("mileage_at_service"),
        performed_at=_parse_dt(d.get("performed_at")),
        source=_enum(ImportSource, d.get("source"), ImportSource.MANUAL),
        metadata=dict(d.get("metadata") or {}),
        row_ref=d.get("row_ref"),
    )


def _money_entity(cls: type, d: dict[str, Any], *, amount_key: str = "amount") -> Any:
    amount = d.get(amount_key) or "0"
    kwargs: dict[str, Any] = {
        "external_id": d.get("external_id"),
        "customer_external_id": d.get("customer_external_id"),
        "vehicle_vin": d.get("vehicle_vin"),
        "amount": Decimal(str(amount)),
        "status": str(d.get("status") or ("paid" if cls is CanonicalInvoice else "open")),
        "issued_at": _parse_dt(d.get("issued_at")),
        "line_items": list(d.get("line_items") or []),
        "source": _enum(ImportSource, d.get("source"), ImportSource.MANUAL),
        "metadata": dict(d.get("metadata") or {}),
        "row_ref": d.get("row_ref"),
    }
    if cls is CanonicalInvoice:
        kwargs["invoice_number"] = d.get("invoice_number")
        kwargs["tax"] = Decimal(str(d.get("tax") or "0"))
    else:
        kwargs["estimate_number"] = d.get("estimate_number")
    return cls(**kwargs)


def _batch_from_dict(d: dict[str, Any] | None) -> NormalizedBatch | None:
    if not d:
        return None
    return NormalizedBatch(
        customers=[_customer_from_dict(x) for x in d.get("customers") or []],
        vehicles=[_vehicle_from_dict(x) for x in d.get("vehicles") or []],
        repairs=[_repair_from_dict(x) for x in d.get("repairs") or []],
        invoices=[_money_entity(CanonicalInvoice, x) for x in d.get("invoices") or []],
        estimates=[_money_entity(CanonicalEstimate, x) for x in d.get("estimates") or []],
        communications=[
            CanonicalCommunication(
                external_id=x.get("external_id"),
                customer_external_id=x.get("customer_external_id"),
                customer_phone=x.get("customer_phone"),
                channel=str(x.get("channel") or "sms"),
                direction=str(x.get("direction") or "inbound"),
                message=str(x.get("message") or ""),
                occurred_at=_parse_dt(x.get("occurred_at")),
                source=_enum(ImportSource, x.get("source"), ImportSource.MANUAL),
                metadata=dict(x.get("metadata") or {}),
                row_ref=x.get("row_ref"),
            )
            for x in d.get("communications") or []
        ],
        appointments=[
            CanonicalAppointment(
                external_id=x.get("external_id"),
                customer_external_id=x.get("customer_external_id"),
                vehicle_vin=x.get("vehicle_vin"),
                start=_parse_dt(x.get("start")),
                end=_parse_dt(x.get("end")),
                repair_type=str(x.get("repair_type") or "general"),
                status=str(x.get("status") or "completed"),
                notes=x.get("notes"),
                source=_enum(ImportSource, x.get("source"), ImportSource.MANUAL),
                metadata=dict(x.get("metadata") or {}),
                row_ref=x.get("row_ref"),
            )
            for x in d.get("appointments") or []
        ],
        recommendations=[
            CanonicalRecommendation(
                external_id=x.get("external_id"),
                vehicle_vin=x.get("vehicle_vin"),
                customer_external_id=x.get("customer_external_id"),
                text=str(x.get("text") or ""),
                priority=str(x.get("priority") or "normal"),
                status=str(x.get("status") or "open"),
                source=_enum(ImportSource, x.get("source"), ImportSource.MANUAL),
                metadata=dict(x.get("metadata") or {}),
                row_ref=x.get("row_ref"),
            )
            for x in d.get("recommendations") or []
        ],
        warnings=[str(w) for w in d.get("warnings") or []],
    )


def _issue_from_dict(d: dict[str, Any]) -> ValidationIssue:
    kind = d.get("entity_kind")
    return ValidationIssue(
        id=_parse_uuid(d.get("id")) or uuid4(),
        severity=_enum(ValidationSeverity, d.get("severity"), ValidationSeverity.WARNING),
        code=str(d.get("code") or ""),
        message=str(d.get("message") or ""),
        entity_kind=_enum(EntityKind, kind, None) if kind else None,
        entity_ref=d.get("entity_ref"),
        details=dict(d.get("details") or {}),
    )


def _dup_from_dict(d: dict[str, Any]) -> DuplicateCandidate:
    resolved_action = d.get("resolved_action")
    return DuplicateCandidate(
        id=_parse_uuid(d.get("id")) or uuid4(),
        entity_kind=_enum(EntityKind, d.get("entity_kind"), EntityKind.CUSTOMER),
        match_type=_enum(DuplicateMatchType, d.get("match_type"), DuplicateMatchType.COMPOSITE),
        confidence=float(d.get("confidence") or 0),
        incoming_ref=str(d.get("incoming_ref") or ""),
        existing_ref=d.get("existing_ref"),
        incoming_snapshot=dict(d.get("incoming_snapshot") or {}),
        existing_snapshot=dict(d.get("existing_snapshot") or {}),
        suggested_action=_enum(MergeAction, d.get("suggested_action"), MergeAction.MERGE),
        resolved_action=_enum(MergeAction, resolved_action, None) if resolved_action else None,
        resolved=bool(d.get("resolved")),
    )


def _report_from_dict(d: dict[str, Any] | None) -> ImportReport | None:
    if not d:
        return None
    job_id = _parse_uuid(d.get("job_id"))
    if job_id is None:
        return None
    entity_counts: dict[str, EntityCountSummary] = {}
    for k, v in (d.get("entity_counts") or {}).items():
        if isinstance(v, dict):
            entity_counts[str(k)] = EntityCountSummary(
                imported=int(v.get("imported") or 0),
                merged=int(v.get("merged") or 0),
                skipped=int(v.get("skipped") or 0),
                failed=int(v.get("failed") or 0),
            )
    return ImportReport(
        job_id=job_id,
        source=_enum(ImportSource, d.get("source"), ImportSource.MANUAL),
        status=_enum(ImportJobStatus, d.get("status"), ImportJobStatus.PENDING),
        entity_counts=entity_counts,
        validation_issues=[_issue_from_dict(x) for x in d.get("validation_issues") or [] if isinstance(x, dict)],
        duplicates_resolved=int(d.get("duplicates_resolved") or 0),
        duplicates_pending=int(d.get("duplicates_pending") or 0),
        duration_ms=int(d.get("duration_ms") or 0),
        warnings=[str(w) for w in d.get("warnings") or []],
        created_at=_parse_dt(d.get("created_at")),
        completed_at=_parse_dt(d.get("completed_at")),
    )


def _pack_options(job: ImportJob) -> str:
    payload = dict(job.options or {})
    payload[_ENGINE_KEY] = {
        "duplicates": _jsonable(job.duplicates),
        "validation_issues": _jsonable(job.validation_issues),
        "batch": _jsonable(job.batch) if job.batch else None,
        "progress_processed": job.progress.processed,
        "progress_total": job.progress.total,
        "progress_updated_at": job.progress.updated_at.isoformat() if job.progress.updated_at else None,
        # credentials intentionally omitted — do not persist secrets
    }
    return _dumps(payload)


def _unpack_options(raw: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _loads(raw)
    if not isinstance(data, dict):
        return {}, {}
    engine = data.pop(_ENGINE_KEY, None)
    if not isinstance(engine, dict):
        engine = {}
    return data, engine


def _job_from_row(row: ImportJobModel) -> ImportJob:
    options, engine = _unpack_options(row.options_json)
    duplicates = [_dup_from_dict(x) for x in engine.get("duplicates") or [] if isinstance(x, dict)]
    issues = [_issue_from_dict(x) for x in engine.get("validation_issues") or [] if isinstance(x, dict)]
    batch = _batch_from_dict(engine.get("batch") if isinstance(engine.get("batch"), dict) else None)
    status = _enum(ImportJobStatus, row.status, ImportJobStatus.PENDING)
    report_raw = _loads(row.report_json)
    return ImportJob(
        id=row.id,
        shop_id=row.shop_id,
        source=_enum(ImportSource, row.source, ImportSource.MANUAL),
        status=status,
        progress=ImportProgress(
            stage=status,
            percent=int(row.progress_percent or 0),
            message=row.progress_message or "",
            processed=int(engine.get("progress_processed") or 0),
            total=int(engine.get("progress_total") or 0),
            updated_at=_parse_dt(engine.get("progress_updated_at")),
        ),
        options=options,
        credentials={},
        raw_payload=None,
        filename=row.filename,
        content_type=row.content_type,
        batch=batch,
        duplicates=duplicates,
        validation_issues=issues,
        report=_report_from_dict(report_raw if isinstance(report_raw, dict) else None),
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _record_from_row(row: ImportRecordModel) -> ImportedRecord:
    payload = _loads(row.payload_json)
    return ImportedRecord(
        id=row.id,
        shop_id=row.shop_id,
        job_id=row.job_id,
        entity_kind=_enum(EntityKind, row.entity_kind, EntityKind.CUSTOMER),
        external_id=row.external_id,
        payload=payload if isinstance(payload, dict) else {},
        merged_into_id=row.merged_into_id,
        created_at=row.created_at,
    )


class SqlAlchemyImportStore:
    """Postgres-backed import job store for production runtime."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        if session is not None and session_factory is None:
            self._fixed_session = session
            self._session_factory = None
        else:
            self._fixed_session = None
            if session_factory is None:
                from app.infrastructure.database import SessionLocal

                session_factory = SessionLocal
            self._session_factory = session_factory
        # Ephemeral process cache — files/credentials are not written to Postgres.
        self._raw_payloads: dict[UUID, bytes] = {}
        self._credentials: dict[UUID, dict[str, Any]] = {}

    def _cache_ephemeral(self, job: ImportJob) -> None:
        if job.raw_payload is not None:
            self._raw_payloads[job.id] = job.raw_payload
        if job.credentials:
            self._credentials[job.id] = dict(job.credentials)

    def _restore_ephemeral(self, job: ImportJob) -> ImportJob:
        if job.raw_payload is None and job.id in self._raw_payloads:
            job.raw_payload = self._raw_payloads[job.id]
        if not job.credentials and job.id in self._credentials:
            job.credentials = dict(self._credentials[job.id])
        return job

    async def _bind(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )

    async def create_job(self, job: ImportJob) -> ImportJob:
        now = datetime.now(timezone.utc)
        job.created_at = now
        job.updated_at = now
        job.progress = ImportProgress(
            stage=job.status,
            percent=0,
            message="Created",
            updated_at=now,
        )
        self._cache_ephemeral(job)

        async def _run(session: AsyncSession) -> ImportJob:
            await self._bind(session, job.shop_id)
            session.add(
                ImportJobModel(
                    id=job.id,
                    shop_id=job.shop_id,
                    source=job.source.value,
                    status=job.status.value,
                    progress_percent=0,
                    progress_message="Created",
                    filename=job.filename,
                    content_type=job.content_type,
                    options_json=_pack_options(job),
                    error=job.error,
                    report_json=_dumps(job.report) if job.report else None,
                    created_at=now,
                    updated_at=now,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )
            )
            await session.commit()
            return job

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def get_job(self, shop_id: UUID, job_id: UUID) -> ImportJob | None:
        async def _run(session: AsyncSession) -> ImportJob | None:
            await self._bind(session, shop_id)
            row = await session.scalar(
                select(ImportJobModel).where(
                    ImportJobModel.id == job_id,
                    ImportJobModel.shop_id == shop_id,
                )
            )
            if row is None:
                return None
            return self._restore_ephemeral(_job_from_row(row))

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def list_jobs(self, shop_id: UUID, *, limit: int = 50) -> list[ImportJob]:
        async def _run(session: AsyncSession) -> list[ImportJob]:
            await self._bind(session, shop_id)
            rows = (
                await session.scalars(
                    select(ImportJobModel)
                    .where(ImportJobModel.shop_id == shop_id)
                    .order_by(ImportJobModel.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [self._restore_ephemeral(_job_from_row(r)) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def save_job(self, job: ImportJob) -> ImportJob:
        now = datetime.now(timezone.utc)
        job.updated_at = now
        self._cache_ephemeral(job)

        async def _run(session: AsyncSession) -> ImportJob:
            await self._bind(session, job.shop_id)
            row = await session.scalar(
                select(ImportJobModel).where(
                    ImportJobModel.id == job.id,
                    ImportJobModel.shop_id == job.shop_id,
                )
            )
            if row is None:
                session.add(
                    ImportJobModel(
                        id=job.id,
                        shop_id=job.shop_id,
                        source=job.source.value,
                        status=job.status.value,
                        progress_percent=int(job.progress.percent or 0),
                        progress_message=job.progress.message,
                        filename=job.filename,
                        content_type=job.content_type,
                        options_json=_pack_options(job),
                        error=job.error,
                        report_json=_dumps(job.report) if job.report else None,
                        created_at=job.created_at or now,
                        updated_at=now,
                        started_at=job.started_at,
                        completed_at=job.completed_at,
                    )
                )
            else:
                row.source = job.source.value
                row.status = job.status.value
                row.progress_percent = int(job.progress.percent or 0)
                row.progress_message = job.progress.message
                row.filename = job.filename
                row.content_type = job.content_type
                row.options_json = _pack_options(job)
                row.error = job.error
                row.report_json = _dumps(job.report) if job.report else None
                row.updated_at = now
                row.started_at = job.started_at
                row.completed_at = job.completed_at

            # Keep duplicate rows in sync for SQL visibility / future queries
            await session.execute(
                delete(ImportDuplicateModel).where(
                    ImportDuplicateModel.job_id == job.id,
                    ImportDuplicateModel.shop_id == job.shop_id,
                )
            )
            for d in job.duplicates:
                session.add(
                    ImportDuplicateModel(
                        id=d.id,
                        shop_id=job.shop_id,
                        job_id=job.id,
                        entity_kind=d.entity_kind.value,
                        match_type=d.match_type.value,
                        confidence=float(d.confidence),
                        incoming_ref=d.incoming_ref,
                        existing_ref=d.existing_ref,
                        incoming_json=_dumps(d.incoming_snapshot),
                        existing_json=_dumps(d.existing_snapshot),
                        suggested_action=d.suggested_action.value,
                        resolved_action=d.resolved_action.value if d.resolved_action else None,
                        resolved=bool(d.resolved),
                        created_at=now,
                    )
                )
            await session.commit()
            return job

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def add_record(self, record: ImportedRecord) -> ImportedRecord:
        now = datetime.now(timezone.utc)
        record.created_at = record.created_at or now

        async def _run(session: AsyncSession) -> ImportedRecord:
            await self._bind(session, record.shop_id)
            session.add(
                ImportRecordModel(
                    id=record.id,
                    shop_id=record.shop_id,
                    job_id=record.job_id,
                    entity_kind=record.entity_kind.value,
                    external_id=record.external_id,
                    payload_json=_dumps(record.payload),
                    merged_into_id=record.merged_into_id,
                    created_at=record.created_at,
                )
            )
            await session.commit()
            return record

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def list_records(
        self, shop_id: UUID, job_id: UUID, *, entity_kind: EntityKind | None = None
    ) -> list[ImportedRecord]:
        async def _run(session: AsyncSession) -> list[ImportedRecord]:
            await self._bind(session, shop_id)
            stmt = select(ImportRecordModel).where(
                ImportRecordModel.shop_id == shop_id,
                ImportRecordModel.job_id == job_id,
            )
            if entity_kind is not None:
                stmt = stmt.where(ImportRecordModel.entity_kind == entity_kind.value)
            rows = (await session.scalars(stmt)).all()
            return [_record_from_row(r) for r in rows]

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)

    async def find_customers_by_phone(self, shop_id: UUID, phone: str) -> list[ImportedRecord]:
        return await self._find(shop_id, EntityKind.CUSTOMER, "phone", phone)

    async def find_customers_by_email(self, shop_id: UUID, email: str) -> list[ImportedRecord]:
        return await self._find(shop_id, EntityKind.CUSTOMER, "email", email.lower())

    async def find_vehicles_by_vin(self, shop_id: UUID, vin: str) -> list[ImportedRecord]:
        return await self._find(shop_id, EntityKind.VEHICLE, "vin", vin.upper())

    async def _find(
        self, shop_id: UUID, kind: EntityKind, field: str, value: str
    ) -> list[ImportedRecord]:
        async def _run(session: AsyncSession) -> list[ImportedRecord]:
            await self._bind(session, shop_id)
            rows = (
                await session.scalars(
                    select(ImportRecordModel).where(
                        ImportRecordModel.shop_id == shop_id,
                        ImportRecordModel.entity_kind == kind.value,
                        ImportRecordModel.merged_into_id.is_(None),
                    )
                )
            ).all()
            out: list[ImportedRecord] = []
            needle = value.lower()
            for row in rows:
                rec = _record_from_row(row)
                if str(rec.payload.get(field) or "").lower() == needle:
                    out.append(rec)
            return out

        if self._fixed_session is not None:
            return await _run(self._fixed_session)
        assert self._session_factory is not None
        async with self._session_factory() as session:
            return await _run(session)
