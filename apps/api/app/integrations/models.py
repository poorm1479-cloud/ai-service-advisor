"""Tenant-scoped integration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.integrations.enums import (
    AuthMethod,
    ConnectionStatus,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TenantContext:
    """Required shop/tenant scope for every integration operation."""

    shop_id: UUID
    tenant_id: UUID | None = None

    def __post_init__(self) -> None:
        # tenant_id defaults to shop_id for single-shop tenants
        if self.tenant_id is None:
            self.tenant_id = self.shop_id

    @property
    def effective_tenant_id(self) -> UUID:
        return self.tenant_id if self.tenant_id is not None else self.shop_id


@dataclass(slots=True)
class ConnectionCredentials:
    method: AuthMethod = AuthMethod.API_KEY
    fields: dict[str, str] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)
    access_token: str | None = None


@dataclass(slots=True)
class IntegrationConnection:
    id: UUID
    shop_id: UUID
    tenant_id: UUID
    provider: IntegrationProvider
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    credentials: ConnectionCredentials | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        credentials: ConnectionCredentials | None = None,
    ) -> IntegrationConnection:
        tid = tenant_id or shop_id
        return cls(
            id=uuid4(),
            shop_id=shop_id,
            tenant_id=tid,
            provider=provider,
            credentials=credentials,
        )


@dataclass(slots=True)
class AdapterManifest:
    provider: IntegrationProvider
    display_name: str
    description: str
    category: IntegrationCategory
    auth_method: AuthMethod
    capabilities: list[IntegrationCapability]
    credential_fields: list[str]
    api_version: str = "v1"
    docs_url: str | None = None


@dataclass(slots=True)
class TenantScopedRecord:
    """Every imported/synced record must carry tenant identity."""

    tenant_id: UUID
    shop_id: UUID
    external_id: str
    provider: IntegrationProvider
    record_type: str
    data: dict[str, Any] = field(default_factory=dict)
    synced_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "shop_id": str(self.shop_id),
            "external_id": self.external_id,
            "provider": self.provider.value,
            "record_type": self.record_type,
            "data": self.data,
            "synced_at": self.synced_at.isoformat(),
        }


@dataclass(slots=True)
class CapabilityRequest:
    capability: IntegrationCapability
    shop_id: UUID
    tenant_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    emit_workflow: bool = True
    invoke_plugins: bool = True

    @property
    def context(self) -> TenantContext:
        return TenantContext(shop_id=self.shop_id, tenant_id=self.tenant_id)


@dataclass(slots=True)
class CapabilityResult:
    ok: bool
    capability: IntegrationCapability
    provider: IntegrationProvider
    shop_id: UUID
    tenant_id: UUID
    records: list[TenantScopedRecord] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    plugin_results: list[dict[str, Any]] = field(default_factory=list)
    workflow_event: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capability": self.capability.value,
            "provider": self.provider.value,
            "shop_id": str(self.shop_id),
            "tenant_id": str(self.tenant_id),
            "records": [r.to_dict() for r in self.records],
            "data": self.data,
            "plugin_results": self.plugin_results,
            "workflow_event": self.workflow_event,
            "error": self.error,
        }
