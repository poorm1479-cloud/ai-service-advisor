"""MCP Integration Hub domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.mcp_hub.enums import (
    AuthMethod,
    ConnectionStatus,
    IntegrationCategory,
    IntegrationProvider,
    InvokeStatus,
    LogLevel,
    PermissionAction,
)


@dataclass(slots=True)
class IntegrationManifest:
    """Describes a pluggable external system."""

    provider: IntegrationProvider
    display_name: str
    description: str
    category: IntegrationCategory
    auth_method: AuthMethod
    api_version: str
    capabilities: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)
    credential_fields: list[str] = field(default_factory=list)
    available: bool = True
    future: bool = False
    docs_url: str | None = None


@dataclass(slots=True)
class ConnectionCredentials:
    """Stored credentials — never returned in full via API."""

    method: AuthMethod
    fields: dict[str, str] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)
    expires_at: datetime | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    def masked(self) -> dict[str, Any]:
        out: dict[str, Any] = {"method": self.method.value, "scopes": list(self.scopes)}
        for k, v in self.fields.items():
            if not v:
                out[k] = ""
            elif len(v) <= 4:
                out[k] = "****"
            else:
                out[k] = f"{v[:2]}***{v[-2:]}"
        if self.access_token:
            out["access_token"] = "****"
        if self.expires_at:
            out["expires_at"] = self.expires_at.isoformat()
        return out


@dataclass(slots=True)
class IntegrationConnection:
    id: UUID
    shop_id: UUID
    provider: IntegrationProvider
    name: str
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    api_version: str = "v1"
    credentials: ConnectionCredentials | None = None
    permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    last_tested_at: datetime | None = None
    connected_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id is None:  # type: ignore[unreachable]
            self.id = uuid4()


@dataclass(slots=True)
class PermissionGrant:
    """Who may invoke which provider actions for a shop."""

    id: UUID
    shop_id: UUID
    principal: str  # role or agent name
    provider: IntegrationProvider
    actions: list[PermissionAction] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 2000
    multiplier: float = 2.0
    retryable_errors: tuple[str, ...] = ("timeout", "rate_limit", "unavailable", "5xx")


@dataclass(slots=True)
class InvokeRequest:
    shop_id: UUID
    provider: IntegrationProvider
    connection_id: UUID | None = None
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    principal: str = "agent"
    api_version: str | None = None
    idempotency_key: str | None = None


@dataclass(slots=True)
class InvokeResult:
    id: UUID
    shop_id: UUID
    provider: IntegrationProvider
    connection_id: UUID | None
    tool: str
    status: InvokeStatus
    attempts: int
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    api_version: str = "v1"
    duration_ms: int = 0
    created_at: datetime | None = None


@dataclass(slots=True)
class IntegrationLogEntry:
    id: UUID
    shop_id: UUID
    provider: IntegrationProvider | None
    connection_id: UUID | None
    level: LogLevel
    event: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True)
class McpToolDescriptor:
    """MCP-compatible tool surface exposed by an integration."""

    name: str
    provider: IntegrationProvider
    description: str
    input_schema: dict[str, Any]
    api_version: str
    required_permission: PermissionAction = PermissionAction.INVOKE
    tags: list[str] = field(default_factory=list)

    def to_mcp(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "provider": self.provider.value,
                "api_version": self.api_version,
                "tags": self.tags,
            },
        }
