"""Canonical import models and job/report structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.import_engine.enums import (
    DuplicateMatchType,
    EntityKind,
    ImportJobStatus,
    ImportSource,
    MergeAction,
    ValidationSeverity,
)


@dataclass(slots=True)
class CanonicalCustomer:
    external_id: str | None = None
    name: str = ""
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalVehicle:
    external_id: str | None = None
    vin: str = ""
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    license_plate: str | None = None
    customer_external_id: str | None = None
    customer_phone: str | None = None
    customer_name: str | None = None
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalRepairHistory:
    external_id: str | None = None
    vehicle_vin: str | None = None
    vehicle_external_id: str | None = None
    customer_external_id: str | None = None
    service_type: str = "general"
    description: str = ""
    cost: Decimal = Decimal("0")
    recommendation: str | None = None
    mileage_at_service: int | None = None
    performed_at: datetime | None = None
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalInvoice:
    external_id: str | None = None
    invoice_number: str | None = None
    customer_external_id: str | None = None
    vehicle_vin: str | None = None
    amount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    status: str = "paid"
    issued_at: datetime | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalEstimate:
    external_id: str | None = None
    estimate_number: str | None = None
    customer_external_id: str | None = None
    vehicle_vin: str | None = None
    amount: Decimal = Decimal("0")
    status: str = "open"
    issued_at: datetime | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalCommunication:
    external_id: str | None = None
    customer_external_id: str | None = None
    customer_phone: str | None = None
    channel: str = "sms"
    direction: str = "inbound"
    message: str = ""
    occurred_at: datetime | None = None
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalAppointment:
    external_id: str | None = None
    customer_external_id: str | None = None
    vehicle_vin: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    repair_type: str = "general"
    status: str = "completed"
    notes: str | None = None
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class CanonicalRecommendation:
    external_id: str | None = None
    vehicle_vin: str | None = None
    customer_external_id: str | None = None
    text: str = ""
    priority: str = "normal"
    status: str = "open"
    source: ImportSource = ImportSource.MANUAL
    metadata: dict[str, Any] = field(default_factory=dict)
    row_ref: str | None = None


@dataclass(slots=True)
class NormalizedBatch:
    customers: list[CanonicalCustomer] = field(default_factory=list)
    vehicles: list[CanonicalVehicle] = field(default_factory=list)
    repairs: list[CanonicalRepairHistory] = field(default_factory=list)
    invoices: list[CanonicalInvoice] = field(default_factory=list)
    estimates: list[CanonicalEstimate] = field(default_factory=list)
    communications: list[CanonicalCommunication] = field(default_factory=list)
    appointments: list[CanonicalAppointment] = field(default_factory=list)
    recommendations: list[CanonicalRecommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            EntityKind.CUSTOMER.value: len(self.customers),
            EntityKind.VEHICLE.value: len(self.vehicles),
            EntityKind.REPAIR_HISTORY.value: len(self.repairs),
            EntityKind.INVOICE.value: len(self.invoices),
            EntityKind.ESTIMATE.value: len(self.estimates),
            EntityKind.COMMUNICATION.value: len(self.communications),
            EntityKind.APPOINTMENT.value: len(self.appointments),
            EntityKind.RECOMMENDATION.value: len(self.recommendations),
        }


@dataclass(slots=True)
class ValidationIssue:
    id: UUID = field(default_factory=uuid4)
    severity: ValidationSeverity = ValidationSeverity.WARNING
    code: str = ""
    message: str = ""
    entity_kind: EntityKind | None = None
    entity_ref: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DuplicateCandidate:
    id: UUID = field(default_factory=uuid4)
    entity_kind: EntityKind = EntityKind.CUSTOMER
    match_type: DuplicateMatchType = DuplicateMatchType.COMPOSITE
    confidence: float = 0.0
    incoming_ref: str = ""
    existing_ref: str | None = None
    incoming_snapshot: dict[str, Any] = field(default_factory=dict)
    existing_snapshot: dict[str, Any] = field(default_factory=dict)
    suggested_action: MergeAction = MergeAction.MERGE
    resolved_action: MergeAction | None = None
    resolved: bool = False


@dataclass(slots=True)
class ImportProgress:
    stage: ImportJobStatus = ImportJobStatus.PENDING
    percent: int = 0
    message: str = ""
    processed: int = 0
    total: int = 0
    updated_at: datetime | None = None


@dataclass(slots=True)
class EntityCountSummary:
    imported: int = 0
    merged: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(slots=True)
class ImportReport:
    job_id: UUID
    source: ImportSource
    status: ImportJobStatus
    entity_counts: dict[str, EntityCountSummary] = field(default_factory=dict)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    duplicates_resolved: int = 0
    duplicates_pending: int = 0
    duration_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class ImportedRecord:
    """Persisted canonical record after apply (in-memory / staging)."""

    id: UUID
    shop_id: UUID
    job_id: UUID
    entity_kind: EntityKind
    external_id: str | None
    payload: dict[str, Any]
    merged_into_id: UUID | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class ImportJob:
    id: UUID
    shop_id: UUID
    source: ImportSource
    status: ImportJobStatus = ImportJobStatus.PENDING
    progress: ImportProgress = field(default_factory=ImportProgress)
    options: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, Any] = field(default_factory=dict)
    raw_payload: bytes | None = None
    filename: str | None = None
    content_type: str | None = None
    batch: NormalizedBatch | None = None
    duplicates: list[DuplicateCandidate] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    report: ImportReport | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
