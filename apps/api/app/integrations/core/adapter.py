"""Base adapter — demo-capable production skeleton with tenant stamping."""

from __future__ import annotations

from typing import Any

from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)
from app.integrations.mapping import (
    map_appointment,
    map_customer,
    map_invoice,
    map_message,
    map_payment,
    map_repair_history,
    map_vehicle,
)
from app.integrations.models import (
    AdapterManifest,
    CapabilityResult,
    ConnectionCredentials,
    IntegrationConnection,
    TenantContext,
    TenantScopedRecord,
)
from app.integrations.security import (
    TenantIsolationError,
    assert_same_tenant,
    filter_records_for_tenant,
)


class BaseAdapter:
    """Concrete base for DMS / accounting / communication / payment adapters."""

    provider: IntegrationProvider
    category: IntegrationCategory
    display_name: str
    description: str
    auth_method: AuthMethod = AuthMethod.API_KEY
    api_version: str = "v1"
    capabilities: list[IntegrationCapability]
    credential_fields: list[str]
    docs_url: str | None = None

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            provider=self.provider,
            display_name=self.display_name,
            description=self.description,
            category=self.category,
            auth_method=self.auth_method,
            capabilities=list(self.capabilities),
            credential_fields=list(self.credential_fields),
            api_version=self.api_version,
            docs_url=self.docs_url,
        )

    def supported_capabilities(self) -> list[IntegrationCapability]:
        return list(self.capabilities)

    async def authenticate(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        missing = [f for f in self.credential_fields if not credentials.fields.get(f)]
        demo = str(credentials.fields.get("demo", "")).lower() in {"1", "true", "yes"}
        if missing and not demo:
            raise ValueError(f"Missing credentials: {', '.join(missing)}")
        if demo:
            credentials.fields["demo"] = "true"
        credentials.method = self.auth_method
        credentials.access_token = credentials.access_token or f"demo-{self.provider.value}-token"
        return credentials

    async def test_connection(self, connection: IntegrationConnection) -> dict[str, Any]:
        if connection.credentials is None:
            raise ValueError("No credentials configured")
        return {
            "ok": True,
            "provider": self.provider.value,
            "api_version": self.api_version,
            "mode": "demo" if connection.credentials.fields.get("demo") else "live",
            "shop_id": str(connection.shop_id),
            "tenant_id": str(connection.tenant_id),
        }

    async def execute(
        self,
        *,
        capability: IntegrationCapability,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        assert_same_tenant(
            expected_shop_id=context.shop_id,
            actual_shop_id=connection.shop_id,
            expected_tenant_id=context.effective_tenant_id,
            actual_tenant_id=connection.tenant_id,
        )
        if capability not in self.supported_capabilities():
            return CapabilityResult(
                ok=False,
                capability=capability,
                provider=self.provider,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                error=f"{self.provider.value} does not support {capability.value}",
            )

        payload = payload or {}
        try:
            records = await self._dispatch(capability, connection, context, payload)
        except Exception as exc:  # noqa: BLE001 — surface as capability result
            return CapabilityResult(
                ok=False,
                capability=capability,
                provider=self.provider,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                error=str(exc),
            )

        safe = filter_records_for_tenant(records, context)
        if len(safe) != len(records):
            raise TenantIsolationError("Adapter returned cross-tenant records")

        return CapabilityResult(
            ok=True,
            capability=capability,
            provider=self.provider,
            shop_id=context.shop_id,
            tenant_id=context.effective_tenant_id,
            records=safe,
            data={"count": len(safe), "mode": self._mode(connection)},
        )

    async def _dispatch(
        self,
        capability: IntegrationCapability,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        handlers = {
            IntegrationCapability.IMPORT_CUSTOMER_DATA: self._import_customers,
            IntegrationCapability.IMPORT_VEHICLE_DATA: self._import_vehicles,
            IntegrationCapability.IMPORT_REPAIR_HISTORY: self._import_repairs,
            IntegrationCapability.SYNC_APPOINTMENT: self._sync_appointments,
            IntegrationCapability.SYNC_INVOICE: self._sync_invoices,
            IntegrationCapability.SYNC_PAYMENT: self._sync_payments,
            IntegrationCapability.SEND_CUSTOMER_MESSAGE: self._send_message,
            IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE: self._receive_message,
        }
        handler = handlers[capability]
        return await handler(connection, context, payload)

    def _mode(self, connection: IntegrationConnection) -> str:
        if connection.credentials and connection.credentials.fields.get("demo"):
            return "demo"
        return "live"

    def _demo_customers(self, context: TenantContext) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{self.provider.value}-cust-1",
                "name": "Alex Rivera",
                "email": "alex@example.com",
                "phone": "+15550101",
            },
            {
                "id": f"{self.provider.value}-cust-2",
                "name": "Jordan Lee",
                "email": "jordan@example.com",
                "phone": "+15550102",
            },
        ]

    def _demo_vehicles(self, context: TenantContext) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{self.provider.value}-veh-1",
                "vin": "1HGBH41JXMN109186",
                "year": 2018,
                "make": "Honda",
                "model": "Civic",
                "customer_id": f"{self.provider.value}-cust-1",
            }
        ]

    def _demo_repairs(self, context: TenantContext) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{self.provider.value}-ro-1",
                "vehicle_id": f"{self.provider.value}-veh-1",
                "customer_id": f"{self.provider.value}-cust-1",
                "description": "Brake pad replacement",
                "status": "completed",
                "total": 320.0,
            }
        ]

    def _demo_appointments(self, context: TenantContext, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.get("appointment"):
            return [payload["appointment"]]
        return [
            {
                "id": f"{self.provider.value}-appt-1",
                "starts_at": payload.get("starts_at", "2026-08-01T15:00:00Z"),
                "customer_id": f"{self.provider.value}-cust-1",
                "vehicle_id": f"{self.provider.value}-veh-1",
                "status": "scheduled",
                "notes": payload.get("notes", "Oil change"),
            }
        ]

    def _demo_invoices(self, context: TenantContext, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.get("invoice"):
            return [payload["invoice"]]
        return [
            {
                "id": f"{self.provider.value}-inv-1",
                "amount": 320.0,
                "currency": "USD",
                "status": "open",
                "customer_id": f"{self.provider.value}-cust-1",
            }
        ]

    def _demo_payments(self, context: TenantContext, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.get("payment"):
            return [payload["payment"]]
        return [
            {
                "id": f"{self.provider.value}-pay-1",
                "amount": 320.0,
                "currency": "USD",
                "status": "succeeded",
                "invoice_id": f"{self.provider.value}-inv-1",
                "customer_id": f"{self.provider.value}-cust-1",
            }
        ]

    async def _import_customers(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("customers") or self._demo_customers(context)
        return [
            map_customer(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _import_vehicles(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("vehicles") or self._demo_vehicles(context)
        return [
            map_vehicle(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _import_repairs(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("repairs") or self._demo_repairs(context)
        return [
            map_repair_history(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _sync_appointments(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("appointments") or self._demo_appointments(context, payload)
        return [
            map_appointment(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _sync_invoices(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("invoices") or self._demo_invoices(context, payload)
        return [
            map_invoice(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _sync_payments(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        raw_items = payload.get("payments") or self._demo_payments(context, payload)
        return [
            map_payment(
                item,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
            )
            for item in raw_items
        ]

    async def _send_message(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        msg = {
            "id": payload.get("id") or f"{self.provider.value}-out-1",
            "to": payload.get("to"),
            "from": payload.get("from"),
            "body": payload.get("body") or payload.get("message") or "",
            "channel": payload.get("channel", self.provider.value),
            "customer_id": payload.get("customer_id"),
        }
        return [
            map_message(
                msg,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
                direction="outbound",
            )
        ]

    async def _receive_message(
        self,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any],
    ) -> list[TenantScopedRecord]:
        msg = payload.get("message") or {
            "id": payload.get("id") or f"{self.provider.value}-in-1",
            "to": payload.get("to"),
            "from": payload.get("from"),
            "body": payload.get("body") or payload.get("message") or "Inbound demo",
            "channel": payload.get("channel", self.provider.value),
            "customer_id": payload.get("customer_id"),
        }
        if isinstance(msg, str):
            msg = {"id": f"{self.provider.value}-in-1", "body": msg}
        return [
            map_message(
                msg,
                shop_id=context.shop_id,
                tenant_id=context.effective_tenant_id,
                provider=self.provider,
                direction="inbound",
            )
        ]
