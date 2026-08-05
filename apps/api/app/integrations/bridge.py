"""Bridge: Adapter results → Plugin Layer → Workflow Engine.

Does not modify plugin business logic or workflow definitions — only invokes
existing capabilities and emits existing domain events.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.integrations.enums import IntegrationCapability
from app.integrations.models import CapabilityResult, TenantScopedRecord
from app.workflows.enums import DomainEventType


# Map integration capabilities → optional plugin capability names (best-effort).
PLUGIN_CAPABILITY_MAP: dict[IntegrationCapability, list[str]] = {
    IntegrationCapability.IMPORT_CUSTOMER_DATA: ["CreateCustomer", "FindCustomer"],
    IntegrationCapability.IMPORT_VEHICLE_DATA: ["CreateVehicle", "FindVehicle"],
    IntegrationCapability.IMPORT_REPAIR_HISTORY: ["AddRepair", "RepairHistory"],
    IntegrationCapability.SYNC_APPOINTMENT: ["BookAppointment", "ValidateAppointment"],
    IntegrationCapability.SYNC_INVOICE: [],
    IntegrationCapability.SYNC_PAYMENT: [],
    IntegrationCapability.SEND_CUSTOMER_MESSAGE: ["AddCommunication"],
    IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE: ["AddCommunication", "CreateConversation"],
}

# Map integration capabilities → workflow domain events (existing enum values).
WORKFLOW_EVENT_MAP: dict[IntegrationCapability, DomainEventType] = {
    IntegrationCapability.IMPORT_CUSTOMER_DATA: DomainEventType.CRM_UPDATED,
    IntegrationCapability.IMPORT_VEHICLE_DATA: DomainEventType.CRM_UPDATED,
    IntegrationCapability.IMPORT_REPAIR_HISTORY: DomainEventType.CRM_UPDATED,
    IntegrationCapability.SYNC_APPOINTMENT: DomainEventType.APPOINTMENT_BOOKED,
    IntegrationCapability.SYNC_INVOICE: DomainEventType.DASHBOARD_UPDATED,
    IntegrationCapability.SYNC_PAYMENT: DomainEventType.INVOICE_PAID,
    IntegrationCapability.SEND_CUSTOMER_MESSAGE: DomainEventType.CRM_UPDATED,
    IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE: DomainEventType.INBOUND_MESSAGE_RECEIVED,
}


class IntegrationBridge:
    """Forward adapter outputs into Plugin Layer and Workflow Engine."""

    async def forward(
        self,
        result: CapabilityResult,
        *,
        invoke_plugins: bool = True,
        emit_workflow: bool = True,
    ) -> CapabilityResult:
        if not result.ok:
            return result

        if invoke_plugins:
            result.plugin_results = await self._invoke_plugins(result)

        if emit_workflow:
            event_name = await self._emit_workflow(result)
            result.workflow_event = event_name

        return result

    async def _invoke_plugins(self, result: CapabilityResult) -> list[dict[str, Any]]:
        """Best-effort plugin invoke — never fails the integration if plugins absent."""
        from app.plugins.framework.context import PluginContext
        from app.plugins.framework.factory import get_plugin_runtime

        targets = PLUGIN_CAPABILITY_MAP.get(result.capability, [])
        if not targets:
            return []

        runtime = get_plugin_runtime()
        ctx = PluginContext.for_shop(result.shop_id, tenant_id=result.tenant_id)

        out: list[dict[str, Any]] = []
        for cap_name in targets:
            try:
                plugin = runtime.plugins.resolve_by_capability(cap_name)
            except Exception:  # noqa: BLE001
                continue
            for record in result.records[:5]:  # bound plugin fan-out
                try:
                    payload = self._plugin_payload(record, result)
                    invoked = await plugin.invoke(cap_name, ctx, **payload)
                    out.append(
                        {
                            "capability": cap_name,
                            "plugin_id": plugin.plugin_id(),
                            "ok": True,
                            "external_id": record.external_id,
                            "result": _safe_preview(invoked),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    out.append(
                        {
                            "capability": cap_name,
                            "plugin_id": getattr(plugin, "plugin_id", lambda: "unknown")(),
                            "ok": False,
                            "external_id": record.external_id,
                            "error": str(exc),
                        }
                    )
                    break  # try next capability target
                else:
                    break  # success on first matching capability
        return out

    async def _emit_workflow(self, result: CapabilityResult) -> str | None:
        event = WORKFLOW_EVENT_MAP.get(result.capability)
        if event is None:
            return None
        from app.workflows.emitter import emit_domain_event

        payload = {
            "source": "integrations",
            "provider": result.provider.value,
            "capability": result.capability.value,
            "tenant_id": str(result.tenant_id),
            "shop_id": str(result.shop_id),
            "record_count": len(result.records),
            "records": [r.to_dict() for r in result.records[:20]],
        }
        await emit_domain_event(
            shop_id=result.shop_id,
            event_type=event,
            payload=payload,
            source="integrations",
        )
        return event.value

    def _plugin_payload(
        self, record: TenantScopedRecord, result: CapabilityResult
    ) -> dict[str, Any]:
        data = dict(record.data)
        data["tenant_id"] = str(result.tenant_id)
        data["shop_id"] = str(result.shop_id)
        data["external_id"] = record.external_id
        data["provider"] = result.provider.value
        data["record_type"] = record.record_type
        return data


def _safe_preview(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _safe_preview(v) for k, v in list(value.items())[:20]}
    if hasattr(value, "__dict__"):
        return {"type": type(value).__name__}
    return str(value)[:200]
