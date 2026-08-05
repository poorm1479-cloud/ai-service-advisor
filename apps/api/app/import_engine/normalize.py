"""Normalize raw connector rows into canonical entities."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.import_engine.enums import ImportSource
from app.import_engine.models import (
    CanonicalAppointment,
    CanonicalCommunication,
    CanonicalCustomer,
    CanonicalEstimate,
    CanonicalInvoice,
    CanonicalRecommendation,
    CanonicalRepairHistory,
    CanonicalVehicle,
    NormalizedBatch,
)
from app.import_engine.vin import normalize_vin

_PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_DIGITS.sub("", phone)
    if not digits:
        return None
    if len(digits) == 10:
        return f"+1{digits}"
    if digits.startswith("1") and len(digits) == 11:
        return f"+{digits}"
    return f"+{digits}"


def normalize_email(email: str | None) -> str | None:
    if not email or not str(email).strip():
        return None
    return str(email).strip().lower()


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(str(name).split()).strip()


def _decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value).replace(",", "").replace("$", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M",
    ):
        try:
            parsed = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def customer_from_dict(row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None) -> CanonicalCustomer:
    return CanonicalCustomer(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        name=normalize_name(row.get("name") or row.get("customer_name")),
        phone=normalize_phone(row.get("phone") or row.get("customer_phone")),
        email=normalize_email(row.get("email")),
        address=(str(row["address"]).strip() if row.get("address") else None),
        source=source,
        metadata={k: v for k, v in row.items() if k.startswith("meta_")},
        row_ref=row_ref or row.get("row_ref"),
    )


def vehicle_from_dict(row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None) -> CanonicalVehicle:
    return CanonicalVehicle(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        vin=normalize_vin(row.get("vin")) or "",
        year=_int(row.get("year")),
        make=(str(row["make"]).strip() if row.get("make") else None),
        model=(str(row["model"]).strip() if row.get("model") else None),
        mileage=_int(row.get("mileage")),
        license_plate=(str(row["license_plate"]).strip().upper() if row.get("license_plate") else None),
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        customer_phone=normalize_phone(row.get("customer_phone") or row.get("phone")),
        customer_name=normalize_name(row.get("customer_name")) or None,
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def repair_from_dict(row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None) -> CanonicalRepairHistory:
    return CanonicalRepairHistory(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        vehicle_vin=normalize_vin(row.get("vehicle_vin") or row.get("vin")),
        vehicle_external_id=str(row.get("vehicle_external_id") or row.get("vehicle_id") or "") or None,
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        service_type=str(row.get("service_type") or row.get("repair_type") or "general"),
        description=str(row.get("description") or row.get("notes") or ""),
        cost=_decimal(row.get("cost") or row.get("amount")),
        recommendation=(str(row["recommendation"]).strip() if row.get("recommendation") else None),
        mileage_at_service=_int(row.get("mileage_at_service") or row.get("mileage")),
        performed_at=_dt(row.get("performed_at") or row.get("date")),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def invoice_from_dict(row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None) -> CanonicalInvoice:
    return CanonicalInvoice(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        invoice_number=str(row.get("invoice_number") or row.get("number") or "") or None,
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        vehicle_vin=normalize_vin(row.get("vehicle_vin") or row.get("vin")),
        amount=_decimal(row.get("amount") or row.get("total")),
        tax=_decimal(row.get("tax")),
        status=str(row.get("status") or "paid"),
        issued_at=_dt(row.get("issued_at") or row.get("date")),
        line_items=list(row.get("line_items") or []),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def estimate_from_dict(row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None) -> CanonicalEstimate:
    return CanonicalEstimate(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        estimate_number=str(row.get("estimate_number") or row.get("number") or "") or None,
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        vehicle_vin=normalize_vin(row.get("vehicle_vin") or row.get("vin")),
        amount=_decimal(row.get("amount") or row.get("total")),
        status=str(row.get("status") or "open"),
        issued_at=_dt(row.get("issued_at") or row.get("date")),
        line_items=list(row.get("line_items") or []),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def communication_from_dict(
    row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None
) -> CanonicalCommunication:
    return CanonicalCommunication(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        customer_phone=normalize_phone(row.get("customer_phone") or row.get("phone")),
        channel=str(row.get("channel") or "sms"),
        direction=str(row.get("direction") or "inbound"),
        message=str(row.get("message") or ""),
        occurred_at=_dt(row.get("occurred_at") or row.get("date")),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def appointment_from_dict(
    row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None
) -> CanonicalAppointment:
    return CanonicalAppointment(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        vehicle_vin=normalize_vin(row.get("vehicle_vin") or row.get("vin")),
        start=_dt(row.get("start") or row.get("start_at")),
        end=_dt(row.get("end") or row.get("end_at")),
        repair_type=str(row.get("repair_type") or "general"),
        status=str(row.get("status") or "completed"),
        notes=(str(row["notes"]).strip() if row.get("notes") else None),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


def recommendation_from_dict(
    row: dict[str, Any], *, source: ImportSource, row_ref: str | None = None
) -> CanonicalRecommendation:
    return CanonicalRecommendation(
        external_id=str(row.get("external_id") or row.get("id") or "") or None,
        vehicle_vin=normalize_vin(row.get("vehicle_vin") or row.get("vin")),
        customer_external_id=str(row.get("customer_external_id") or row.get("customer_id") or "") or None,
        text=str(row.get("text") or row.get("recommendation") or ""),
        priority=str(row.get("priority") or "normal"),
        status=str(row.get("status") or "open"),
        source=source,
        row_ref=row_ref or row.get("row_ref"),
    )


_ENTITY_BUILDERS = {
    "customers": customer_from_dict,
    "customer": customer_from_dict,
    "vehicles": vehicle_from_dict,
    "vehicle": vehicle_from_dict,
    "repairs": repair_from_dict,
    "repair_history": repair_from_dict,
    "repair": repair_from_dict,
    "invoices": invoice_from_dict,
    "invoice": invoice_from_dict,
    "estimates": estimate_from_dict,
    "estimate": estimate_from_dict,
    "communications": communication_from_dict,
    "communication": communication_from_dict,
    "appointments": appointment_from_dict,
    "appointment": appointment_from_dict,
    "recommendations": recommendation_from_dict,
    "recommendation": recommendation_from_dict,
}

_BATCH_ATTR = {
    "customers": "customers",
    "customer": "customers",
    "vehicles": "vehicles",
    "vehicle": "vehicles",
    "repairs": "repairs",
    "repair_history": "repairs",
    "repair": "repairs",
    "invoices": "invoices",
    "invoice": "invoices",
    "estimates": "estimates",
    "estimate": "estimates",
    "communications": "communications",
    "communication": "communications",
    "appointments": "appointments",
    "appointment": "appointments",
    "recommendations": "recommendations",
    "recommendation": "recommendations",
}


def build_batch_from_sections(
    sections: dict[str, list[dict[str, Any]]],
    *,
    source: ImportSource,
) -> NormalizedBatch:
    batch = NormalizedBatch()
    for key, rows in sections.items():
        builder = _ENTITY_BUILDERS.get(key.lower())
        attr = _BATCH_ATTR.get(key.lower())
        if not builder or not attr:
            batch.warnings.append(f"Unknown section skipped: {key}")
            continue
        bucket = getattr(batch, attr)
        for i, row in enumerate(rows):
            bucket.append(builder(row, source=source, row_ref=row.get("row_ref") or f"{key}:{i+1}"))
    return batch


def merge_batches(*batches: NormalizedBatch) -> NormalizedBatch:
    out = NormalizedBatch()
    for b in batches:
        out.customers.extend(b.customers)
        out.vehicles.extend(b.vehicles)
        out.repairs.extend(b.repairs)
        out.invoices.extend(b.invoices)
        out.estimates.extend(b.estimates)
        out.communications.extend(b.communications)
        out.appointments.extend(b.appointments)
        out.recommendations.extend(b.recommendations)
        out.warnings.extend(b.warnings)
    return out
