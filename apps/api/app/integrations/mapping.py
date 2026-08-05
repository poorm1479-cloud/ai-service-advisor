"""Canonical data mapping between external systems and ASA domain shapes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.integrations.enums import IntegrationProvider
from app.integrations.models import TenantScopedRecord
from app.integrations.security import stamp_tenant


def map_customer(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(
        raw.get("id")
        or raw.get("customer_id")
        or raw.get("external_id")
        or raw.get("uuid")
        or ""
    )
    data = stamp_tenant(
        {
            "full_name": raw.get("full_name") or raw.get("name") or raw.get("display_name"),
            "email": raw.get("email"),
            "phone": raw.get("phone") or raw.get("mobile"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-customer-unknown",
        provider=provider,
        record_type="customer",
        data=data,
    )


def map_vehicle(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("vehicle_id") or raw.get("vin") or "")
    data = stamp_tenant(
        {
            "vin": raw.get("vin"),
            "year": raw.get("year"),
            "make": raw.get("make"),
            "model": raw.get("model"),
            "customer_external_id": raw.get("customer_id") or raw.get("customer_external_id"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-vehicle-unknown",
        provider=provider,
        record_type="vehicle",
        data=data,
    )


def map_repair_history(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("job_id") or raw.get("ro_number") or "")
    data = stamp_tenant(
        {
            "vehicle_external_id": raw.get("vehicle_id") or raw.get("vehicle_external_id"),
            "customer_external_id": raw.get("customer_id"),
            "description": raw.get("description") or raw.get("summary") or raw.get("title"),
            "status": raw.get("status"),
            "completed_at": raw.get("completed_at") or raw.get("closed_at"),
            "total": raw.get("total") or raw.get("amount"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-repair-unknown",
        provider=provider,
        record_type="repair_history",
        data=data,
    )


def map_appointment(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("appointment_id") or "")
    data = stamp_tenant(
        {
            "starts_at": raw.get("starts_at") or raw.get("start") or raw.get("scheduled_at"),
            "ends_at": raw.get("ends_at") or raw.get("end"),
            "customer_external_id": raw.get("customer_id"),
            "vehicle_external_id": raw.get("vehicle_id"),
            "status": raw.get("status"),
            "notes": raw.get("notes") or raw.get("reason"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-appt-unknown",
        provider=provider,
        record_type="appointment",
        data=data,
    )


def map_invoice(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("invoice_id") or raw.get("doc_number") or "")
    data = stamp_tenant(
        {
            "amount": raw.get("amount") or raw.get("total"),
            "currency": raw.get("currency", "USD"),
            "status": raw.get("status"),
            "customer_external_id": raw.get("customer_id"),
            "line_items": raw.get("line_items") or raw.get("lines") or [],
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-invoice-unknown",
        provider=provider,
        record_type="invoice",
        data=data,
    )


def map_payment(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("payment_id") or raw.get("charge_id") or "")
    data = stamp_tenant(
        {
            "amount": raw.get("amount"),
            "currency": raw.get("currency", "USD"),
            "status": raw.get("status"),
            "invoice_external_id": raw.get("invoice_id"),
            "customer_external_id": raw.get("customer_id"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-payment-unknown",
        provider=provider,
        record_type="payment",
        data=data,
    )


def map_message(
    raw: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID,
    provider: IntegrationProvider,
    direction: str,
) -> TenantScopedRecord:
    external_id = str(raw.get("id") or raw.get("message_id") or raw.get("sid") or "")
    data = stamp_tenant(
        {
            "direction": direction,
            "channel": raw.get("channel") or provider.value,
            "to": raw.get("to"),
            "from": raw.get("from") or raw.get("from_"),
            "body": raw.get("body") or raw.get("text") or raw.get("message"),
            "customer_external_id": raw.get("customer_id"),
            "external": raw,
        },
        shop_id=shop_id,
        tenant_id=tenant_id,
    )
    return TenantScopedRecord(
        tenant_id=tenant_id,
        shop_id=shop_id,
        external_id=external_id or f"{provider.value}-msg-unknown",
        provider=provider,
        record_type="message",
        data=data,
    )
