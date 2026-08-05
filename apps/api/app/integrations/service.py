"""Integrations orchestration service — External → Adapter → Registry → Bridge."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.integrations.bridge import IntegrationBridge
from app.integrations.core.registry import AdapterRegistry, get_adapter_registry
from app.integrations.enums import (
    ConnectionStatus,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)
from app.integrations.models import (
    CapabilityRequest,
    CapabilityResult,
    ConnectionCredentials,
    IntegrationConnection,
    TenantContext,
)
from app.integrations.security import TenantIsolationError, require_tenant_context
from app.integrations.store import InMemoryIntegrationStore, IntegrationStorePort


class IntegrationsService:
    def __init__(
        self,
        *,
        store: IntegrationStorePort | None = None,
        registry: AdapterRegistry | None = None,
        bridge: IntegrationBridge | None = None,
    ) -> None:
        self._store = store or InMemoryIntegrationStore()
        self._registry = registry or get_adapter_registry()
        self._bridge = bridge or IntegrationBridge()

    def list_adapters(self, category: IntegrationCategory | None = None) -> list[dict[str, Any]]:
        adapters = (
            self._registry.list_by_category(category)
            if category is not None
            else self._registry.list()
        )
        return [
            {
                "provider": a.provider.value,
                "category": a.category.value,
                "display_name": a.manifest().display_name,
                "description": a.manifest().description,
                "capabilities": [c.value for c in a.supported_capabilities()],
                "auth_method": a.manifest().auth_method.value,
                "credential_fields": a.manifest().credential_fields,
                "docs_url": a.manifest().docs_url,
            }
            for a in adapters
        ]

    def capability_matrix(self) -> dict[str, list[str]]:
        matrix: dict[str, list[str]] = {}
        for cap in IntegrationCapability:
            matrix[cap.value] = [p.value for p in self._registry.providers_for(cap)]
        return matrix

    async def connect(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        credentials: dict[str, str] | None = None,
        tenant_id: UUID | None = None,
        demo: bool = True,
    ) -> IntegrationConnection:
        ctx = require_tenant_context(shop_id, tenant_id)
        try:
            adapter = self._registry.get(provider)
        except KeyError as exc:
            # Rebuild once — covers stale in-process registry after adapter registration.
            from app.integrations.core.registry import build_default_registry

            self._registry = build_default_registry()
            try:
                adapter = self._registry.get(provider)
            except KeyError:
                raise ValueError(str(exc).strip("'\"")) from exc
        fields = dict(credentials or {})
        if demo:
            fields["demo"] = "true"
        creds = await adapter.authenticate(ConnectionCredentials(fields=fields))

        existing = await self._store.get_by_provider(shop_id, provider)
        if existing:
            existing.credentials = creds
            existing.status = ConnectionStatus.CONNECTED
            existing.tenant_id = ctx.effective_tenant_id
            existing.updated_at = datetime.now(timezone.utc)
            return await self._store.save(existing)

        conn = IntegrationConnection.create(
            shop_id=shop_id,
            tenant_id=ctx.effective_tenant_id,
            provider=provider,
            credentials=creds,
        )
        conn.status = ConnectionStatus.CONNECTED
        return await self._store.save(conn)

    async def disconnect(self, *, shop_id: UUID, provider: IntegrationProvider) -> bool:
        conn = await self._store.get_by_provider(shop_id, provider)
        if conn is None:
            return False
        conn.status = ConnectionStatus.DISCONNECTED
        conn.updated_at = datetime.now(timezone.utc)
        await self._store.save(conn)
        return True

    async def list_connections(self, shop_id: UUID) -> list[dict[str, Any]]:
        conns = await self._store.list_for_shop(shop_id)
        return [
            {
                "id": str(c.id),
                "shop_id": str(c.shop_id),
                "tenant_id": str(c.tenant_id),
                "provider": c.provider.value,
                "status": c.status.value,
            }
            for c in conns
        ]

    async def test_connection(
        self, *, shop_id: UUID, provider: IntegrationProvider
    ) -> dict[str, Any]:
        conn = await self._require_connection(shop_id, provider)
        adapter = self._registry.get(provider)
        return await adapter.test_connection(conn)

    async def execute(
        self,
        request: CapabilityRequest,
        *,
        provider: IntegrationProvider | None = None,
    ) -> CapabilityResult:
        ctx = request.context
        if provider is not None:
            adapter = self._registry.get(provider)
        else:
            adapter = self._registry.resolve(request.capability)
        conn = await self._ensure_connection(ctx, adapter.provider)
        result = await adapter.execute(
            capability=request.capability,
            connection=conn,
            context=ctx,
            payload=request.payload,
        )
        return await self._bridge.forward(
            result,
            invoke_plugins=request.invoke_plugins,
            emit_workflow=request.emit_workflow,
        )

    async def import_customer_data(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.IMPORT_CUSTOMER_DATA,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def import_vehicle_data(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.IMPORT_VEHICLE_DATA,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def import_repair_history(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.IMPORT_REPAIR_HISTORY,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def sync_appointment(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.SYNC_APPOINTMENT,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def sync_invoice(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.SYNC_INVOICE,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def sync_payment(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.SYNC_PAYMENT,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def send_customer_message(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.SEND_CUSTOMER_MESSAGE,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def receive_customer_message(
        self,
        *,
        shop_id: UUID,
        provider: IntegrationProvider,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        emit_workflow: bool = True,
        invoke_plugins: bool = False,
    ) -> CapabilityResult:
        return await self.execute(
            CapabilityRequest(
                capability=IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload or {},
                emit_workflow=emit_workflow,
                invoke_plugins=invoke_plugins,
            ),
            provider=provider,
        )

    async def _require_connection(
        self, shop_id: UUID, provider: IntegrationProvider
    ) -> IntegrationConnection:
        conn = await self._store.get_by_provider(shop_id, provider)
        if conn is None or conn.status != ConnectionStatus.CONNECTED:
            raise LookupError(f"No connected integration for {provider.value}")
        if conn.shop_id != shop_id:
            raise TenantIsolationError("Cross-shop connection access denied")
        return conn

    async def _ensure_connection(
        self, ctx: TenantContext, provider: IntegrationProvider
    ) -> IntegrationConnection:
        conn = await self._store.get_by_provider(ctx.shop_id, provider)
        if conn and conn.status == ConnectionStatus.CONNECTED:
            return conn
        return await self.connect(
            shop_id=ctx.shop_id,
            provider=provider,
            tenant_id=ctx.effective_tenant_id,
            demo=True,
        )
