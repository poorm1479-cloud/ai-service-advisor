"""Optional Integration Plugin — registers Import*/Sync*/Message* into Plugin Framework.

Does not replace CRM / Workflow / existing plugins. Delegates to IntegrationsService.
"""

from __future__ import annotations

from typing import Any

from app.integrations.enums import IntegrationCapability, IntegrationProvider
from app.integrations.models import CapabilityRequest
from app.plugins.framework.context import PluginContext


class IntegrationPlugin:
    def __init__(self) -> None:
        self._initialized = False

    def plugin_id(self) -> str:
        return "integrations"

    def plugin_name(self) -> str:
        return "External Integration Layer"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Adapter layer for DMS, accounting, communication, and payment systems. "
            "Routes through Capability Registry into existing plugins and workflows."
        )

    def supported_capabilities(self) -> list[str]:
        return [c.value for c in IntegrationCapability]

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        from app.integrations.factory import get_integrations_runtime

        runtime = get_integrations_runtime()
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "adapters": len(runtime.registry.list()),
            "capabilities": len(self.supported_capabilities()),
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        from app.integrations.factory import get_integrations_runtime

        shop_id = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id is required for integration capabilities")
        tenant_id = kwargs.get("tenant_id") or (context.tenant_id if context else None) or shop_id
        provider_raw = kwargs.get("provider")
        if provider_raw is None:
            raise ValueError("provider is required for integration capabilities")
        provider = (
            provider_raw
            if isinstance(provider_raw, IntegrationProvider)
            else IntegrationProvider(str(provider_raw))
        )
        cap = IntegrationCapability(capability)
        payload = dict(kwargs.get("payload") or {})
        for key in (
            "customers",
            "vehicles",
            "repairs",
            "appointments",
            "invoices",
            "payments",
            "message",
            "body",
            "to",
            "from",
        ):
            if key in kwargs and key not in payload:
                payload[key] = kwargs[key]

        result = await get_integrations_runtime().service.execute(
            CapabilityRequest(
                capability=cap,
                shop_id=shop_id,
                tenant_id=tenant_id,
                payload=payload,
                emit_workflow=bool(kwargs.get("emit_workflow", True)),
                invoke_plugins=bool(kwargs.get("invoke_plugins", False)),
            ),
            provider=provider,
        )
        return result.to_dict()
