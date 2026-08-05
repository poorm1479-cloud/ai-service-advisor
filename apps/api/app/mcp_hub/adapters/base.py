"""Shared helpers for modular integration adapters."""

from __future__ import annotations

from typing import Any

from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider
from app.mcp_hub.models import (
    ConnectionCredentials,
    IntegrationConnection,
    IntegrationManifest,
    InvokeRequest,
    McpToolDescriptor,
    PermissionAction,
)


class BaseAdapter:
    """Concrete base with demo-mode authenticate / test / invoke."""

    provider: IntegrationProvider
    display_name: str
    description: str
    category: IntegrationCategory
    auth_method: AuthMethod
    api_version: str = "v1"
    capabilities: list[str]
    required_scopes: list[str]
    credential_fields: list[str]
    tool_defs: list[tuple[str, str, dict[str, Any], list[str]]]
    available: bool = True
    future: bool = False
    docs_url: str | None = None

    def manifest(self) -> IntegrationManifest:
        return IntegrationManifest(
            provider=self.provider,
            display_name=self.display_name,
            description=self.description,
            category=self.category,
            auth_method=self.auth_method,
            api_version=self.api_version,
            capabilities=list(self.capabilities),
            required_scopes=list(self.required_scopes),
            credential_fields=list(self.credential_fields),
            available=self.available,
            future=self.future,
            docs_url=self.docs_url,
        )

    def tools(self) -> list[McpToolDescriptor]:
        return [
            McpToolDescriptor(
                name=name,
                provider=self.provider,
                description=desc,
                input_schema=schema,
                api_version=self.api_version,
                required_permission=PermissionAction.INVOKE,
                tags=tags,
            )
            for name, desc, schema, tags in self.tool_defs
        ]

    async def authenticate(self, credentials: ConnectionCredentials) -> ConnectionCredentials:
        missing = [f for f in self.credential_fields if not credentials.fields.get(f)]
        if missing and not credentials.fields.get("demo"):
            # Allow demo=true to skip real secrets in local/dev
            if credentials.fields.get("demo", "").lower() in {"1", "true", "yes"}:
                credentials.fields["demo"] = "true"
            else:
                raise ValueError(f"Missing credentials: {', '.join(missing)}")
        credentials.method = self.auth_method
        if not credentials.scopes:
            credentials.scopes = list(self.required_scopes)
        credentials.access_token = credentials.access_token or f"demo-{self.provider.value}-token"
        return credentials

    async def test_connection(self, connection: IntegrationConnection) -> dict[str, Any]:
        if connection.credentials is None:
            raise ValueError("No credentials configured")
        return {
            "ok": True,
            "provider": self.provider.value,
            "api_version": connection.api_version or self.api_version,
            "latency_ms": 12,
            "mode": "demo" if connection.credentials.fields.get("demo") else "live",
        }

    async def invoke(
        self,
        connection: IntegrationConnection,
        request: InvokeRequest,
    ) -> dict[str, Any]:
        tool_names = {t[0] for t in self.tool_defs}
        if request.tool and request.tool not in tool_names:
            raise ValueError(f"Unknown tool '{request.tool}' for {self.provider.value}")
        return {
            "provider": self.provider.value,
            "tool": request.tool,
            "arguments": request.arguments,
            "connection_id": str(connection.id),
            "api_version": connection.api_version or self.api_version,
            "result": "ok",
            "data": self._demo_payload(request),
        }

    def _demo_payload(self, request: InvokeRequest) -> dict[str, Any]:
        return {"echo": request.arguments or {}, "status": "accepted"}
