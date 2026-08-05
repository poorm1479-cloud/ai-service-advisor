"""Integration adapter protocol and registry."""

from __future__ import annotations

from typing import Any, Protocol

from app.mcp_hub.enums import IntegrationProvider
from app.mcp_hub.models import (
    ConnectionCredentials,
    IntegrationConnection,
    IntegrationManifest,
    InvokeRequest,
    McpToolDescriptor,
)


class IntegrationAdapter(Protocol):
    """Pluggable external-system adapter."""

    provider: IntegrationProvider

    def manifest(self) -> IntegrationManifest: ...

    def tools(self) -> list[McpToolDescriptor]: ...

    async def authenticate(self, credentials: ConnectionCredentials) -> ConnectionCredentials: ...

    async def test_connection(self, connection: IntegrationConnection) -> dict[str, Any]: ...

    async def invoke(
        self,
        connection: IntegrationConnection,
        request: InvokeRequest,
    ) -> dict[str, Any]: ...


_REGISTRY: dict[IntegrationProvider, IntegrationAdapter] | None = None


def build_adapter_registry() -> dict[IntegrationProvider, IntegrationAdapter]:
    from app.mcp_hub.adapters.autoleap import AutoLeapAdapter
    from app.mcp_hub.adapters.email import EmailAdapter
    from app.mcp_hub.adapters.facebook import FacebookAdapter
    from app.mcp_hub.adapters.future import FutureAdapter
    from app.mcp_hub.adapters.google_business import GoogleBusinessAdapter
    from app.mcp_hub.adapters.google_calendar import GoogleCalendarAdapter
    from app.mcp_hub.adapters.mitchell import MitchellAdapter
    from app.mcp_hub.adapters.shopmonkey import ShopmonkeyAdapter
    from app.mcp_hub.adapters.stripe import StripeAdapter
    from app.mcp_hub.adapters.tekmetric import TekmetricAdapter
    from app.mcp_hub.adapters.twilio import TwilioAdapter

    adapters: list[IntegrationAdapter] = [
        TekmetricAdapter(),
        ShopmonkeyAdapter(),
        AutoLeapAdapter(),
        MitchellAdapter(),
        GoogleCalendarAdapter(),
        GoogleBusinessAdapter(),
        TwilioAdapter(),
        StripeAdapter(),
        FacebookAdapter(),
        EmailAdapter(),
        FutureAdapter(),
    ]
    return {a.provider: a for a in adapters}


def get_adapter(provider: IntegrationProvider) -> IntegrationAdapter:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_adapter_registry()
    try:
        return _REGISTRY[provider]
    except KeyError as exc:
        raise KeyError(f"Unknown integration provider: {provider}") from exc


def list_adapters() -> list[IntegrationAdapter]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_adapter_registry()
    return list(_REGISTRY.values())


def reset_adapter_registry() -> None:
    global _REGISTRY
    _REGISTRY = None
