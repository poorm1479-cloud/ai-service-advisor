"""Integration adapter protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.integrations.enums import IntegrationCapability, IntegrationCategory, IntegrationProvider
from app.integrations.models import (
    AdapterManifest,
    CapabilityResult,
    ConnectionCredentials,
    IntegrationConnection,
    TenantContext,
)


@runtime_checkable
class IntegrationAdapter(Protocol):
    """Every external system communicates through an adapter."""

    provider: IntegrationProvider
    category: IntegrationCategory

    def manifest(self) -> AdapterManifest: ...

    def supported_capabilities(self) -> list[IntegrationCapability]: ...

    async def authenticate(
        self,
        credentials: ConnectionCredentials,
    ) -> ConnectionCredentials: ...

    async def test_connection(
        self,
        connection: IntegrationConnection,
    ) -> dict[str, Any]: ...

    async def execute(
        self,
        *,
        capability: IntegrationCapability,
        connection: IntegrationConnection,
        context: TenantContext,
        payload: dict[str, Any] | None = None,
    ) -> CapabilityResult: ...
