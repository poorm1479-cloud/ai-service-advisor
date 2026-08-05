"""Import job store port + in-memory implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from app.import_engine.enums import EntityKind, ImportJobStatus, ImportSource
from app.import_engine.models import ImportedRecord, ImportJob, ImportProgress


class ImportStorePort(Protocol):
    async def create_job(self, job: ImportJob) -> ImportJob: ...

    async def get_job(self, shop_id: UUID, job_id: UUID) -> ImportJob | None: ...

    async def list_jobs(self, shop_id: UUID, *, limit: int = 50) -> list[ImportJob]: ...

    async def save_job(self, job: ImportJob) -> ImportJob: ...

    async def add_record(self, record: ImportedRecord) -> ImportedRecord: ...

    async def list_records(
        self, shop_id: UUID, job_id: UUID, *, entity_kind: EntityKind | None = None
    ) -> list[ImportedRecord]: ...

    async def find_customers_by_phone(self, shop_id: UUID, phone: str) -> list[ImportedRecord]: ...

    async def find_customers_by_email(self, shop_id: UUID, email: str) -> list[ImportedRecord]: ...

    async def find_vehicles_by_vin(self, shop_id: UUID, vin: str) -> list[ImportedRecord]: ...


class InMemoryImportStore:
    def __init__(self) -> None:
        self.jobs: dict[UUID, ImportJob] = {}
        self.records: dict[UUID, list[ImportedRecord]] = {}

    async def create_job(self, job: ImportJob) -> ImportJob:
        now = datetime.now(timezone.utc)
        job.created_at = now
        job.updated_at = now
        job.progress = ImportProgress(stage=job.status, percent=0, message="Created", updated_at=now)
        self.jobs[job.id] = job
        self.records.setdefault(job.id, [])
        return job

    async def get_job(self, shop_id: UUID, job_id: UUID) -> ImportJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.shop_id != shop_id:
            return None
        return job

    async def list_jobs(self, shop_id: UUID, *, limit: int = 50) -> list[ImportJob]:
        items = [j for j in self.jobs.values() if j.shop_id == shop_id]
        items.sort(key=lambda j: j.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]

    async def save_job(self, job: ImportJob) -> ImportJob:
        job.updated_at = datetime.now(timezone.utc)
        self.jobs[job.id] = job
        return job

    async def add_record(self, record: ImportedRecord) -> ImportedRecord:
        self.records.setdefault(record.job_id, []).append(record)
        return record

    async def list_records(
        self, shop_id: UUID, job_id: UUID, *, entity_kind: EntityKind | None = None
    ) -> list[ImportedRecord]:
        items = [r for r in self.records.get(job_id, []) if r.shop_id == shop_id]
        if entity_kind:
            items = [r for r in items if r.entity_kind == entity_kind]
        return items

    async def find_customers_by_phone(self, shop_id: UUID, phone: str) -> list[ImportedRecord]:
        return self._find(shop_id, EntityKind.CUSTOMER, "phone", phone)

    async def find_customers_by_email(self, shop_id: UUID, email: str) -> list[ImportedRecord]:
        return self._find(shop_id, EntityKind.CUSTOMER, "email", email.lower())

    async def find_vehicles_by_vin(self, shop_id: UUID, vin: str) -> list[ImportedRecord]:
        return self._find(shop_id, EntityKind.VEHICLE, "vin", vin.upper())

    def _find(self, shop_id: UUID, kind: EntityKind, field: str, value: str) -> list[ImportedRecord]:
        out: list[ImportedRecord] = []
        for records in self.records.values():
            for r in records:
                if r.shop_id != shop_id or r.entity_kind != kind or r.merged_into_id:
                    continue
                if str(r.payload.get(field) or "").lower() == value.lower():
                    out.append(r)
        return out


def new_job(
    *,
    shop_id: UUID,
    source: ImportSource,
    options: dict | None = None,
    credentials: dict | None = None,
) -> ImportJob:
    return ImportJob(
        id=uuid4(),
        shop_id=shop_id,
        source=source,
        status=ImportJobStatus.PENDING,
        options=options or {},
        credentials=credentials or {},
    )
