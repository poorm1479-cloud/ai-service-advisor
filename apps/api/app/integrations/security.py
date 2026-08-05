"""Tenant isolation guards for the External Integration Layer."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.integrations.models import TenantContext, TenantScopedRecord


class TenantIsolationError(PermissionError):
    """Raised when an operation would cross shop/tenant boundaries."""


def require_tenant_context(shop_id: UUID | None, tenant_id: UUID | None = None) -> TenantContext:
    if shop_id is None:
        raise TenantIsolationError("shop_id (tenant scope) is required")
    return TenantContext(shop_id=shop_id, tenant_id=tenant_id)


def assert_same_tenant(
    *,
    expected_shop_id: UUID,
    actual_shop_id: UUID,
    expected_tenant_id: UUID | None = None,
    actual_tenant_id: UUID | None = None,
) -> None:
    if actual_shop_id != expected_shop_id:
        raise TenantIsolationError("Cross-shop data access denied")
    if expected_tenant_id is not None and actual_tenant_id is not None:
        if actual_tenant_id != expected_tenant_id:
            raise TenantIsolationError("Cross-tenant data access denied")


def stamp_tenant(
    data: dict[str, Any],
    *,
    shop_id: UUID,
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    """Ensure outbound/inbound payloads always include tenant identity."""
    tid = tenant_id or shop_id
    stamped = dict(data)
    stamped["shop_id"] = str(shop_id)
    stamped["tenant_id"] = str(tid)
    return stamped


def validate_record_tenant(record: TenantScopedRecord, ctx: TenantContext) -> TenantScopedRecord:
    assert_same_tenant(
        expected_shop_id=ctx.shop_id,
        actual_shop_id=record.shop_id,
        expected_tenant_id=ctx.effective_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    if not record.tenant_id:
        raise TenantIsolationError("Imported record missing tenant_id")
    return record


def filter_records_for_tenant(
    records: list[TenantScopedRecord],
    ctx: TenantContext,
) -> list[TenantScopedRecord]:
    """Drop any record that does not match the active tenant (defense in depth)."""
    out: list[TenantScopedRecord] = []
    for r in records:
        if r.shop_id == ctx.shop_id and r.tenant_id == ctx.effective_tenant_id:
            out.append(r)
    return out
