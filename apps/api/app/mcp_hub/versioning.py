"""API version negotiation for integrations."""

from __future__ import annotations

from app.mcp_hub.adapters import get_adapter
from app.mcp_hub.enums import IntegrationProvider


class VersionMismatch(ValueError):
    pass


SUPPORTED: dict[IntegrationProvider, tuple[str, ...]] = {
    IntegrationProvider.TEKMETRIC: ("v1",),
    IntegrationProvider.SHOPMONKEY: ("v1",),
    IntegrationProvider.AUTOLEAP: ("v1",),
    IntegrationProvider.MITCHELL: ("v1",),
    IntegrationProvider.GOOGLE_CALENDAR: ("v3", "v1"),
    IntegrationProvider.GOOGLE_BUSINESS: ("v1",),
    IntegrationProvider.TWILIO: ("v1",),
    IntegrationProvider.STRIPE: ("2024-06-20", "v1"),
    IntegrationProvider.FACEBOOK: ("v19.0", "v18.0", "v1"),
    IntegrationProvider.EMAIL: ("v1",),
    IntegrationProvider.FUTURE: ("v0", "v1"),
}


class VersionService:
    def default_version(self, provider: IntegrationProvider) -> str:
        return get_adapter(provider).manifest().api_version

    def supported(self, provider: IntegrationProvider) -> list[str]:
        return list(SUPPORTED.get(provider, (self.default_version(provider),)))

    def resolve(self, provider: IntegrationProvider, requested: str | None) -> str:
        if not requested:
            return self.default_version(provider)
        supported = self.supported(provider)
        if requested not in supported:
            raise VersionMismatch(
                f"Unsupported api_version '{requested}' for {provider.value}; "
                f"supported={supported}"
            )
        return requested
