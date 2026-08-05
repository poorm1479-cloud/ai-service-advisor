"""Adapter + capability registries for the External Integration Layer."""

from __future__ import annotations

from app.integrations.core.interface import IntegrationAdapter
from app.integrations.enums import IntegrationCapability, IntegrationCategory, IntegrationProvider


class AdapterRegistry:
    """Registers adapters by provider and resolves capability → adapters."""

    def __init__(self) -> None:
        self._by_provider: dict[IntegrationProvider, IntegrationAdapter] = {}
        self._by_capability: dict[IntegrationCapability, list[IntegrationProvider]] = {}

    def register(self, adapter: IntegrationAdapter, *, replace: bool = False) -> None:
        if adapter.provider in self._by_provider and not replace:
            raise ValueError(f"Adapter already registered: {adapter.provider.value}")
        # Unbind previous capability index if replacing
        if replace and adapter.provider in self._by_provider:
            old = self._by_provider[adapter.provider]
            for cap in old.supported_capabilities():
                providers = self._by_capability.get(cap, [])
                self._by_capability[cap] = [p for p in providers if p != adapter.provider]

        self._by_provider[adapter.provider] = adapter
        for cap in adapter.supported_capabilities():
            bucket = self._by_capability.setdefault(cap, [])
            if adapter.provider not in bucket:
                bucket.append(adapter.provider)

    def get(self, provider: IntegrationProvider) -> IntegrationAdapter:
        adapter = self._by_provider.get(provider)
        if adapter is not None:
            return adapter
        # Value-based fallback (survives enum identity mismatches after reload)
        for key, registered in self._by_provider.items():
            if key.value == provider.value:
                return registered
        raise KeyError(f"Unknown integration provider: {provider.value}")

    def list(self) -> list[IntegrationAdapter]:
        return list(self._by_provider.values())

    def list_by_category(self, category: IntegrationCategory) -> list[IntegrationAdapter]:
        return [a for a in self._by_provider.values() if a.category == category]

    def providers_for(self, capability: IntegrationCapability) -> list[IntegrationProvider]:
        return list(self._by_capability.get(capability, []))

    def adapters_for(self, capability: IntegrationCapability) -> list[IntegrationAdapter]:
        return [self.get(p) for p in self.providers_for(capability)]

    def resolve(
        self,
        capability: IntegrationCapability,
        *,
        provider: IntegrationProvider | None = None,
    ) -> IntegrationAdapter:
        if provider is not None:
            adapter = self.get(provider)
            if capability not in adapter.supported_capabilities():
                raise LookupError(
                    f"{provider.value} does not support capability {capability.value}"
                )
            return adapter
        adapters = self.adapters_for(capability)
        if not adapters:
            raise LookupError(f"No adapter registered for capability {capability.value}")
        return adapters[0]


_registry: AdapterRegistry | None = None


def build_default_registry() -> AdapterRegistry:
    from app.integrations.accounting.quickbooks import QuickBooksAdapter
    from app.integrations.communication.email import EmailAdapter
    from app.integrations.communication.twilio import TwilioAdapter
    from app.integrations.dms.autoleap import AutoLeapAdapter
    from app.integrations.dms.mitchell import MitchellAdapter
    from app.integrations.dms.shopmonkey import ShopmonkeyAdapter
    from app.integrations.dms.tekmetric import TekmetricAdapter
    from app.integrations.payment.stripe import StripeAdapter

    registry = AdapterRegistry()
    for adapter in (
        ShopmonkeyAdapter(),
        TekmetricAdapter(),
        AutoLeapAdapter(),
        MitchellAdapter(),
        QuickBooksAdapter(),
        TwilioAdapter(),
        EmailAdapter(),
        StripeAdapter(),
    ):
        registry.register(adapter)
    return registry


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry


def reset_adapter_registry() -> None:
    global _registry
    _registry = None
