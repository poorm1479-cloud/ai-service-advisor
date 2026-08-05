"""Import Engine orchestration service."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.agents.base.agent import AgentContext
from app.agents.customer.models import CustomerResolveRequest
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.factory import AgentRuntime
from app.agents.vehicle.models import RepairRecord, VehicleResolveRequest
from app.domain.enums import CommunicationChannel, CommunicationDirection
from app.import_engine.connectors.base import ConnectorContext, get_connector
from app.import_engine.enums import (
    EntityKind,
    ImportJobStatus,
    ImportSource,
    MergeAction,
    ValidationSeverity,
)
from app.import_engine.models import (
    CanonicalCustomer,
    CanonicalVehicle,
    EntityCountSummary,
    ImportedRecord,
    ImportJob,
    ImportProgress,
    ImportReport,
    NormalizedBatch,
    ValidationIssue,
)
from app.import_engine.store import ImportStorePort, new_job
from app.import_engine.validation import ValidationEngine


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
    if isinstance(obj, ImportSource):
        return obj.value
    return obj


class ImportEngineService:
    def __init__(
        self,
        *,
        store: ImportStorePort,
        validation: ValidationEngine,
        agents: AgentRuntime,
    ) -> None:
        self._store = store
        self._validation = validation
        self._agents = agents

    async def create_job(
        self,
        *,
        shop_id: UUID,
        source: ImportSource,
        options: dict[str, Any] | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> ImportJob:
        job = new_job(shop_id=shop_id, source=source, options=options, credentials=credentials)
        return await self._store.create_job(job)

    async def attach_upload(
        self,
        *,
        shop_id: UUID,
        job_id: UUID,
        payload: bytes,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> ImportJob:
        job = await self._require_job(shop_id, job_id)
        job.raw_payload = payload
        job.filename = filename
        job.content_type = content_type
        # Align connector with uploaded file when UI source/extension disagree.
        inferred = self._infer_source_from_upload(filename, payload)
        if inferred is not None and job.source in (ImportSource.CSV, ImportSource.EXCEL):
            job.source = inferred
        await self._set_progress(job, ImportJobStatus.UPLOADING, 10, "File uploaded")
        return await self._store.save_job(job)

    @staticmethod
    def _infer_source_from_upload(
        filename: str | None, payload: bytes
    ) -> ImportSource | None:
        name = (filename or "").lower()
        if name.endswith((".csv", ".tsv", ".txt")):
            return ImportSource.CSV
        if name.endswith((".xlsx", ".xlsm", ".xltx")):
            return ImportSource.EXCEL
        # Filename missing/ambiguous — sniff content
        if payload.startswith(b"PK"):
            return ImportSource.EXCEL
        sample = payload[:2048]
        if sample and b"\x00" not in sample:
            try:
                text = sample.decode("utf-8-sig")
            except UnicodeDecodeError:
                return None
            if "," in text or "\t" in text or ";" in text:
                return ImportSource.CSV
        return None

    async def set_manual_sections(
        self,
        *,
        shop_id: UUID,
        job_id: UUID,
        sections: dict[str, list[dict[str, Any]]],
    ) -> ImportJob:
        job = await self._require_job(shop_id, job_id)
        job.options = {**job.options, "sections": sections}
        return await self._store.save_job(job)

    async def run(
        self,
        *,
        shop_id: UUID,
        job_id: UUID,
        auto_apply: bool = False,
    ) -> ImportJob:
        job = await self._require_job(shop_id, job_id)
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        try:
            await self._set_progress(job, ImportJobStatus.PARSING, 20, "Extracting source data")
            batch = await self._extract(job)
            await self._set_progress(job, ImportJobStatus.NORMALIZING, 40, "Normalizing entities")
            job.batch = batch

            await self._set_progress(job, ImportJobStatus.VALIDATING, 60, "AI validation")
            issues, duplicates = await self._validation.validate(
                batch, shop_id=shop_id, store=self._store
            )
            job.validation_issues = issues
            job.duplicates = duplicates

            pending = [d for d in duplicates if not d.resolved and d.confidence >= 0.7]
            if pending and not auto_apply:
                await self._set_progress(
                    job,
                    ImportJobStatus.AWAITING_RESOLUTION,
                    75,
                    f"{len(pending)} duplicate(s) need resolution",
                )
                job.report = self._build_report(job, applied=False)
                return await self._store.save_job(job)

            if auto_apply:
                for dup in job.duplicates:
                    if not dup.resolved and dup.confidence >= 0.7:
                        dup.resolved_action = dup.suggested_action
                        dup.resolved = True

            return await self.apply(shop_id=shop_id, job_id=job_id)
        except Exception as exc:  # noqa: BLE001 — surface as job failure
            job.status = ImportJobStatus.FAILED
            job.error = str(exc)
            job.progress = ImportProgress(
                stage=ImportJobStatus.FAILED,
                percent=100,
                message=str(exc),
                updated_at=datetime.now(timezone.utc),
            )
            job.completed_at = datetime.now(timezone.utc)
            return await self._store.save_job(job)

    async def resolve_duplicates(
        self,
        *,
        shop_id: UUID,
        job_id: UUID,
        resolutions: list[dict[str, Any]],
        apply_after: bool = True,
    ) -> ImportJob:
        job = await self._require_job(shop_id, job_id)
        by_id = {str(d.id): d for d in job.duplicates}
        for item in resolutions:
            dup = by_id.get(str(item.get("duplicate_id")))
            if not dup:
                continue
            action = MergeAction(str(item.get("action") or MergeAction.MERGE.value))
            dup.resolved_action = action
            dup.resolved = True

        pending = [d for d in job.duplicates if not d.resolved and d.confidence >= 0.7]
        if pending:
            await self._set_progress(
                job,
                ImportJobStatus.AWAITING_RESOLUTION,
                75,
                f"{len(pending)} duplicate(s) still pending",
            )
            return await self._store.save_job(job)

        if apply_after:
            return await self.apply(shop_id=shop_id, job_id=job_id)
        return await self._store.save_job(job)

    async def apply(self, *, shop_id: UUID, job_id: UUID) -> ImportJob:
        job = await self._require_job(shop_id, job_id)
        if job.batch is None:
            raise ValueError("Job has no normalized batch; run import first")

        await self._set_progress(job, ImportJobStatus.APPLYING, 85, "Applying import")
        batch = self._apply_duplicate_resolutions(job)
        counts = await self._persist_batch(job, batch)
        job.completed_at = datetime.now(timezone.utc)
        job.report = self._build_report(job, applied=True, counts=counts)
        await self._set_progress(job, ImportJobStatus.COMPLETED, 100, "Import completed")
        return await self._store.save_job(job)

    async def get_job(self, shop_id: UUID, job_id: UUID) -> ImportJob:
        return await self._require_job(shop_id, job_id)

    async def list_jobs(self, shop_id: UUID, *, limit: int = 50) -> list[ImportJob]:
        return await self._store.list_jobs(shop_id, limit=limit)

    async def _extract(self, job: ImportJob) -> NormalizedBatch:
        connector = get_connector(job.source)
        ctx = ConnectorContext(
            shop_id=job.shop_id,
            source=job.source,
            credentials=job.credentials,
            options=job.options,
            payload=job.raw_payload,
            filename=job.filename,
            content_type=job.content_type,
            manual_sections=job.options.get("sections"),
        )
        return await connector.extract(ctx)

    def _apply_duplicate_resolutions(self, job: ImportJob) -> NormalizedBatch:
        assert job.batch is not None
        batch = job.batch
        skip_customer_refs: set[str] = set()
        skip_vehicle_refs: set[str] = set()
        customer_merges: dict[str, str] = {}
        vehicle_merges: dict[str, str] = {}

        for dup in job.duplicates:
            action = dup.resolved_action
            if action is None:
                if dup.confidence >= 0.9:
                    action = dup.suggested_action
                else:
                    continue
            if action == MergeAction.SKIP:
                if dup.entity_kind == EntityKind.CUSTOMER:
                    skip_customer_refs.add(dup.incoming_ref)
                else:
                    skip_vehicle_refs.add(dup.incoming_ref)
            elif action in (MergeAction.MERGE, MergeAction.KEEP_EXISTING):
                if dup.entity_kind == EntityKind.CUSTOMER:
                    customer_merges[dup.incoming_ref] = dup.existing_ref or dup.incoming_ref
                    skip_customer_refs.add(dup.incoming_ref)
                else:
                    vehicle_merges[dup.incoming_ref] = dup.existing_ref or dup.incoming_ref
                    skip_vehicle_refs.add(dup.incoming_ref)

        customers = self._merge_customers(batch.customers, skip_customer_refs, customer_merges)
        vehicles = self._merge_vehicles(batch.vehicles, skip_vehicle_refs, vehicle_merges)

        return NormalizedBatch(
            customers=customers,
            vehicles=vehicles,
            repairs=batch.repairs,
            invoices=batch.invoices,
            estimates=batch.estimates,
            communications=batch.communications,
            appointments=batch.appointments,
            recommendations=batch.recommendations,
            warnings=list(batch.warnings),
        )

    def _merge_customers(
        self,
        items: list[CanonicalCustomer],
        skip_refs: set[str],
        merges: dict[str, str],
    ) -> list[CanonicalCustomer]:
        by_ref: dict[str, CanonicalCustomer] = {}
        order: list[str] = []
        for i, c in enumerate(items):
            ref = c.row_ref or c.external_id or f"customer:{i}"
            if ref in skip_refs:
                target_ref = merges.get(ref)
                if target_ref and target_ref in by_ref:
                    by_ref[target_ref] = self._validation.merge_customer(by_ref[target_ref], c)
                continue
            by_ref[ref] = c
            order.append(ref)
        return [by_ref[r] for r in order if r in by_ref]

    def _merge_vehicles(
        self,
        items: list[CanonicalVehicle],
        skip_refs: set[str],
        merges: dict[str, str],
    ) -> list[CanonicalVehicle]:
        by_ref: dict[str, CanonicalVehicle] = {}
        order: list[str] = []
        for i, v in enumerate(items):
            ref = v.row_ref or v.external_id or v.vin or f"vehicle:{i}"
            if ref in skip_refs:
                target_ref = merges.get(ref)
                if target_ref and target_ref in by_ref:
                    by_ref[target_ref] = self._validation.merge_vehicle(by_ref[target_ref], v)
                continue
            by_ref[ref] = v
            order.append(ref)
        return [by_ref[r] for r in order if r in by_ref]

    async def _persist_batch(
        self, job: ImportJob, batch: NormalizedBatch
    ) -> dict[str, EntityCountSummary]:
        counts: dict[str, EntityCountSummary] = {k.value: EntityCountSummary() for k in EntityKind}
        agent_ctx = AgentContext(shop_id=job.shop_id, correlation_id=str(job.id))
        ports = ports_from_agents(
            customer=self._agents.customer,
            vehicle=self._agents.vehicle,
            scheduling=self._agents.scheduling,
            crm=self._agents.crm,
        )
        # Maps for linking related entities after CRM create
        customer_by_ext: dict[str, UUID] = {}
        customer_by_phone: dict[str, UUID] = {}
        vehicle_by_vin: dict[str, UUID] = {}
        vehicle_by_ext: dict[str, UUID] = {}

        async def persist(kind: EntityKind, external_id: str | None, payload: Any, ref: str) -> None:
            try:
                await self._store.add_record(
                    ImportedRecord(
                        id=uuid4(),
                        shop_id=job.shop_id,
                        job_id=job.id,
                        entity_kind=kind,
                        external_id=external_id,
                        payload=_jsonable(payload),
                        created_at=datetime.now(timezone.utc),
                    )
                )
                counts[kind.value].imported += 1
            except Exception as exc:  # noqa: BLE001
                counts[kind.value].failed += 1
                job.validation_issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="persist_failed",
                        message=str(exc),
                        entity_kind=kind,
                        entity_ref=ref,
                    )
                )

        def _record_issue(kind: EntityKind, ref: str, message: str) -> None:
            counts[kind.value].failed += 1
            job.validation_issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="crm_apply_failed",
                    message=message,
                    entity_kind=kind,
                    entity_ref=ref,
                )
            )

        for i, c in enumerate(batch.customers):
            ref = c.row_ref or f"customer:{i}"
            try:
                result = await self._agents.customer.resolve(
                    CustomerResolveRequest(
                        name=c.name or "Unknown",
                        phone=c.phone,
                        email=c.email,
                        create_if_missing=True,
                    ),
                    agent_ctx,
                )
                decision = collect_decision(result)
                if decision is not None:
                    applied = await apply_decisions(
                        shop_id=job.shop_id,
                        decisions=[decision],
                        ports=ports,
                        context=agent_ctx,
                    )
                    if applied and applied.customer_result and applied.customer_result.customer:
                        result = type(result)(success=True, data=applied.customer_result)
                customer = result.data.customer if result.data else None
                if customer is None:
                    raise RuntimeError("Customer resolve returned no profile")
                if c.external_id:
                    customer_by_ext[c.external_id] = customer.id
                if customer.phone:
                    digits = "".join(ch for ch in customer.phone if ch.isdigit())
                    if digits:
                        customer_by_phone[digits] = customer.id
                agent_ctx.customer_id = customer.id
                await persist(EntityKind.CUSTOMER, c.external_id, c, ref)
            except Exception as exc:  # noqa: BLE001
                _record_issue(EntityKind.CUSTOMER, ref, str(exc))

        for i, v in enumerate(batch.vehicles):
            ref = v.row_ref or f"vehicle:{i}"
            if not v.vin:
                _record_issue(EntityKind.VEHICLE, ref, "VIN required to import vehicle")
                continue
            customer_id = None
            if v.customer_external_id and v.customer_external_id in customer_by_ext:
                customer_id = customer_by_ext[v.customer_external_id]
            elif v.customer_phone:
                digits = "".join(ch for ch in v.customer_phone if ch.isdigit())
                customer_id = customer_by_phone.get(digits)
            if customer_id is None and agent_ctx.customer_id is not None and len(batch.customers) == 1:
                customer_id = agent_ctx.customer_id
            try:
                result = await self._agents.vehicle.resolve(
                    VehicleResolveRequest(
                        vin=v.vin,
                        year=v.year,
                        make=v.make,
                        model=v.model,
                        mileage=v.mileage,
                        customer_id=customer_id,
                        create_if_missing=True,
                    ),
                    agent_ctx,
                )
                decision = collect_decision(result)
                if decision is not None:
                    applied = await apply_decisions(
                        shop_id=job.shop_id,
                        decisions=[decision],
                        ports=ports,
                        context=agent_ctx,
                    )
                    if applied and applied.vehicle_result and applied.vehicle_result.vehicle:
                        from app.agents.base.agent import AgentResult

                        result = AgentResult.ok(applied.vehicle_result)
                vehicle = result.data.vehicle if result.data else None
                if vehicle is None:
                    raise RuntimeError("Vehicle resolve returned no record")
                vehicle_by_vin[vehicle.vin.upper()] = vehicle.id
                if v.external_id:
                    vehicle_by_ext[v.external_id] = vehicle.id
                agent_ctx.vehicle_id = vehicle.id
                await persist(EntityKind.VEHICLE, v.external_id, v, ref)
            except Exception as exc:  # noqa: BLE001
                _record_issue(EntityKind.VEHICLE, ref, str(exc))

        directory = getattr(self._agents.vehicle, "directory", None)
        for i, r in enumerate(batch.repairs):
            ref = r.row_ref or f"repair:{i}"
            vehicle_id = None
            if r.vehicle_vin:
                vehicle_id = vehicle_by_vin.get(r.vehicle_vin.upper())
                if vehicle_id is None and directory is not None:
                    try:
                        existing = await directory.find_by_vin(job.shop_id, r.vehicle_vin)
                        if existing:
                            vehicle_id = existing.id
                            vehicle_by_vin[existing.vin.upper()] = existing.id
                    except Exception:  # noqa: BLE001
                        pass
            if r.vehicle_external_id and r.vehicle_external_id in vehicle_by_ext:
                vehicle_id = vehicle_by_ext[r.vehicle_external_id]
            if directory is None or not hasattr(directory, "add_repair"):
                _record_issue(
                    EntityKind.REPAIR_HISTORY,
                    ref,
                    "Repair history could not be stored: vehicle directory unavailable",
                )
                continue
            if vehicle_id is None:
                _record_issue(
                    EntityKind.REPAIR_HISTORY,
                    ref,
                    "Repair history skipped: no matching vehicle (VIN or vehicle_external_id required)",
                )
                continue
            try:
                await directory.add_repair(
                    job.shop_id,
                    RepairRecord(
                        id=uuid4(),
                        vehicle_id=vehicle_id,
                        service_type=r.service_type or "general",
                        description=r.description or r.service_type or "Imported repair",
                        cost=float(r.cost or 0),
                        performed_at=r.performed_at,
                        recommendation=r.recommendation,
                    ),
                )
                await persist(EntityKind.REPAIR_HISTORY, r.external_id, r, ref)
            except Exception as exc:  # noqa: BLE001
                _record_issue(EntityKind.REPAIR_HISTORY, ref, str(exc))

        for i, inv in enumerate(batch.invoices):
            await persist(EntityKind.INVOICE, inv.external_id, inv, inv.row_ref or f"invoice:{i}")
        for i, est in enumerate(batch.estimates):
            await persist(EntityKind.ESTIMATE, est.external_id, est, est.row_ref or f"estimate:{i}")

        for i, com in enumerate(batch.communications):
            ref = com.row_ref or f"comm:{i}"
            customer_id = None
            if com.customer_external_id and com.customer_external_id in customer_by_ext:
                customer_id = customer_by_ext[com.customer_external_id]
            elif com.customer_phone:
                digits = "".join(ch for ch in com.customer_phone if ch.isdigit())
                customer_id = customer_by_phone.get(digits)
            if customer_id is None:
                await persist(EntityKind.COMMUNICATION, com.external_id, com, ref)
                continue
            try:
                await self._persist_communication(job.shop_id, customer_id, com)
                await persist(EntityKind.COMMUNICATION, com.external_id, com, ref)
            except Exception as exc:  # noqa: BLE001
                _record_issue(EntityKind.COMMUNICATION, ref, str(exc))

        for i, appt in enumerate(batch.appointments):
            await persist(EntityKind.APPOINTMENT, appt.external_id, appt, appt.row_ref or f"appt:{i}")
        for i, rec in enumerate(batch.recommendations):
            await persist(EntityKind.RECOMMENDATION, rec.external_id, rec, rec.row_ref or f"rec:{i}")

        counts[EntityKind.CUSTOMER.value].merged = sum(
            1
            for d in job.duplicates
            if d.entity_kind == EntityKind.CUSTOMER
            and d.resolved_action in (MergeAction.MERGE, MergeAction.KEEP_EXISTING)
        )
        counts[EntityKind.VEHICLE.value].merged = sum(
            1
            for d in job.duplicates
            if d.entity_kind == EntityKind.VEHICLE
            and d.resolved_action in (MergeAction.MERGE, MergeAction.KEEP_EXISTING)
        )
        counts[EntityKind.CUSTOMER.value].skipped = sum(
            1
            for d in job.duplicates
            if d.entity_kind == EntityKind.CUSTOMER and d.resolved_action == MergeAction.SKIP
        )
        counts[EntityKind.VEHICLE.value].skipped = sum(
            1
            for d in job.duplicates
            if d.entity_kind == EntityKind.VEHICLE and d.resolved_action == MergeAction.SKIP
        )
        return counts

    async def _persist_communication(
        self, shop_id: UUID, customer_id: UUID, com: Any
    ) -> None:
        """Best-effort write into SQL CRM communication history when available."""
        try:
            from app.application.crm_service import CrmService
            from app.infrastructure.database import SessionLocal
            from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
        except Exception:  # noqa: BLE001
            return

        channel_raw = (getattr(com, "channel", None) or "sms").lower()
        channel_map = {
            "phone": CommunicationChannel.PHONE,
            "sms": CommunicationChannel.SMS,
            "email": CommunicationChannel.EMAIL,
            "facebook": CommunicationChannel.FACEBOOK,
            "website_chat": CommunicationChannel.WEBSITE_CHAT,
            "walk_in": CommunicationChannel.WALK_IN,
        }
        channel = channel_map.get(channel_raw, CommunicationChannel.SMS)
        direction_raw = (getattr(com, "direction", None) or "inbound").lower()
        direction = (
            CommunicationDirection.OUTGOING
            if direction_raw in {"outbound", "outgoing", "out"}
            else CommunicationDirection.INCOMING
        )
        message = (getattr(com, "message", None) or "").strip() or "Imported communication"
        async with SessionLocal() as session:
            uow = SqlAlchemyUnitOfWork(session)
            service = CrmService(uow)
            await service.add_communication(
                shop_id=shop_id,
                customer_id=customer_id,
                channel=channel,
                message=message,
                direction=direction,
                created_at=getattr(com, "occurred_at", None),
            )

    def _build_report(
        self,
        job: ImportJob,
        *,
        applied: bool,
        counts: dict[str, EntityCountSummary] | None = None,
    ) -> ImportReport:
        started = job.started_at or job.created_at or datetime.now(timezone.utc)
        ended = job.completed_at or datetime.now(timezone.utc)
        duration = int((ended - started).total_seconds() * 1000)
        pending = sum(1 for d in job.duplicates if not d.resolved and d.confidence >= 0.7)
        resolved = sum(1 for d in job.duplicates if d.resolved)
        if counts is None:
            entity_counts = {
                k: EntityCountSummary(imported=v) for k, v in (job.batch.counts() if job.batch else {}).items()
            }
        else:
            entity_counts = counts
        return ImportReport(
            job_id=job.id,
            source=job.source,
            status=ImportJobStatus.COMPLETED if applied else job.status,
            entity_counts=entity_counts,
            validation_issues=list(job.validation_issues),
            duplicates_resolved=resolved,
            duplicates_pending=pending,
            duration_ms=max(duration, 0),
            warnings=list(job.batch.warnings) if job.batch else [],
            created_at=job.created_at,
            completed_at=job.completed_at if applied else None,
        )

    async def _require_job(self, shop_id: UUID, job_id: UUID) -> ImportJob:
        job = await self._store.get_job(shop_id, job_id)
        if job is None:
            raise LookupError("Import job not found")
        return job

    async def _set_progress(
        self, job: ImportJob, status: ImportJobStatus, percent: int, message: str
    ) -> None:
        job.status = status
        job.progress = ImportProgress(
            stage=status,
            percent=percent,
            message=message,
            updated_at=datetime.now(timezone.utc),
        )
        await self._store.save_job(job)
