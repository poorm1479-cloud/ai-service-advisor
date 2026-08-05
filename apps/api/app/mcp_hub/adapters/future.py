"""Placeholder adapter for future integrations."""

from __future__ import annotations

from typing import Any

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider
from app.mcp_hub.models import ConnectionCredentials, IntegrationConnection, InvokeRequest


class FutureAdapter(BaseAdapter):
    provider = IntegrationProvider.FUTURE
    display_name = "Future Integrations"
    description = "Reserved slot for upcoming MCP connectors — register via hub registry."
    category = IntegrationCategory.EXTENSIBILITY
    auth_method = AuthMethod.NONE
    api_version = "v0"
    capabilities = ["registry.extend"]
    required_scopes = []
    credential_fields = []
    available = True
    future = True
    tool_defs = [
        (
            "future.ping",
            "Health ping for future connector slots",
            {"type": "object", "properties": {"name": {"type": "string"}}},
            ["future"],
        ),
    ]

    async def authenticate(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        credentials.method = AuthMethod.NONE
        credentials.access_token = "future-placeholder"
        return credentials

    async def test_connection(self, connection: IntegrationConnection) -> dict[str, Any]:
        return {"ok": True, "provider": "future", "message": "Slot ready for registration"}

    async def invoke(
        self,
        connection: IntegrationConnection,
        request: InvokeRequest,
    ) -> dict[str, Any]:
        return {
            "provider": "future",
            "tool": request.tool or "future.ping",
            "status": "not_implemented",
            "message": "Register a concrete adapter to enable this slot",
            "arguments": request.arguments,
        }
