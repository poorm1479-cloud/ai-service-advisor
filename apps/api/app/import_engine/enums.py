"""Import engine enumerations."""

from __future__ import annotations

from enum import StrEnum


class ImportSource(StrEnum):
    TEKMETRIC = "tekmetric"
    SHOPMONKEY = "shopmonkey"
    AUTOLEAP = "autoleap"
    MITCHELL = "mitchell"
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    OCR = "ocr"
    MANUAL = "manual"


# Lower = higher priority when resolving multi-source conflicts.
SOURCE_PRIORITY: dict[ImportSource, int] = {
    ImportSource.TEKMETRIC: 1,
    ImportSource.SHOPMONKEY: 1,
    ImportSource.AUTOLEAP: 1,
    ImportSource.MITCHELL: 1,
    ImportSource.CSV: 2,
    ImportSource.EXCEL: 3,
    ImportSource.PDF: 4,
    ImportSource.OCR: 5,
    ImportSource.MANUAL: 6,
}


class ImportJobStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    VALIDATING = "validating"
    AWAITING_RESOLUTION = "awaiting_resolution"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EntityKind(StrEnum):
    CUSTOMER = "customer"
    VEHICLE = "vehicle"
    REPAIR_HISTORY = "repair_history"
    INVOICE = "invoice"
    ESTIMATE = "estimate"
    COMMUNICATION = "communication"
    APPOINTMENT = "appointment"
    RECOMMENDATION = "recommendation"


class DuplicateMatchType(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    NAME = "name"
    VIN = "vin"
    LICENSE_PLATE = "license_plate"
    COMPOSITE = "composite"


class MergeAction(StrEnum):
    KEEP_EXISTING = "keep_existing"
    KEEP_INCOMING = "keep_incoming"
    MERGE = "merge"
    SKIP = "skip"


class ValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
