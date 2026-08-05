"""In-memory store for MCP Integration Hub."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.mcp_hub.enums import IntegrationProvider
from app.mcp_hub.models import (
    IntegrationConnection,
    IntegrationLogEntry,
    InvokeResult,
    PermissionGrant,
)


class McpHubStorePort(Protocol):
    def save_connection(self, connection: IntegrationConnection) -> IntegrationConnection: ...

    def get_connection(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection | None: ...

    def list_connections(
        self,
        shop_id: UUID,
        *,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationConnection]: ...

    def delete_connection(self, shop_id: UUID, connection_id: UUID) -> bool: ...

    def save_permission(self, grant: PermissionGrant) -> PermissionGrant: ...

    def list_permissions(
        self,
        shop_id: UUID,
        *,
        principal: str | None = None,
        provider: IntegrationProvider | None = None,
    ) -> list[PermissionGrant]: ...

    def append_log(self, entry: IntegrationLogEntry) -> IntegrationLogEntry: ...

    def list_logs(
        self,
        shop_id: UUID,
        *,
        limit: int = 100,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationLogEntry]: ...

    def save_invoke(self, result: InvokeResult) -> InvokeResult: ...

    def list_invokes(self, shop_id: UUID, *, limit: int = 50) -> list[InvokeResult]: ...


class InMemoryMcpHubStore:
    def __init__(self) -> None:
        self._connections: dict[UUID, IntegrationConnection] = {}
        self._permissions: dict[UUID, PermissionGrant] = {}
        self._logs: list[IntegrationLogEntry] = []
        self._invokes: list[InvokeResult] = []

    def save_connection(self, connection: IntegrationConnection) -> IntegrationConnection:
        now = datetime.now(timezone.utc)
        if connection.created_at is None:
            connection.created_at = now
        connection.updated_at = now
        self._connections[connection.id] = connection
        return connection

    def get_connection(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection | None:
        conn = self._connections.get(connection_id)
        if conn is None or conn.shop_id != shop_id:
            return None
        return conn

    def list_connections(
        self,
        shop_id: UUID,
        *,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationConnection]:
        rows = [c for c in self._connections.values() if c.shop_id == shop_id]
        if provider is not None:
            rows = [c for c in rows if c.provider == provider]
        return sorted(rows, key=lambda c: c.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def delete_connection(self, shop_id: UUID, connection_id: UUID) -> bool:
        conn = self.get_connection(shop_id, connection_id)
        if conn is None:
            return False
        del self._connections[connection_id]
        return True

    def save_permission(self, grant: PermissionGrant) -> PermissionGrant:
        if grant.created_at is None:
            grant.created_at = datetime.now(timezone.utc)
        self._permissions[grant.id] = grant
        return grant

    def list_permissions(
        self,
        shop_id: UUID,
        *,
        principal: str | None = None,
        provider: IntegrationProvider | None = None,
    ) -> list[PermissionGrant]:
        rows = [p for p in self._permissions.values() if p.shop_id == shop_id]
        if principal is not None:
            rows = [p for p in rows if p.principal == principal]
        if provider is not None:
            rows = [p for p in rows if p.provider == provider]
        return rows

    def append_log(self, entry: IntegrationLogEntry) -> IntegrationLogEntry:
        self._logs.append(entry)
        if len(self._logs) > 5000:
            self._logs = self._logs[-2500:]
        return entry

    def list_logs(
        self,
        shop_id: UUID,
        *,
        limit: int = 100,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationLogEntry]:
        rows = [e for e in self._logs if e.shop_id == shop_id]
        if provider is not None:
            rows = [e for e in rows if e.provider == provider]
        return list(reversed(rows[-limit:]))

    def save_invoke(self, result: InvokeResult) -> InvokeResult:
        self._invokes.append(result)
        if len(self._invokes) > 2000:
            self._invokes = self._invokes[-1000:]
        return result

    def list_invokes(self, shop_id: UUID, *, limit: int = 50) -> list[InvokeResult]:
        rows = [r for r in self._invokes if r.shop_id == shop_id]
        return list(reversed(rows[-limit:]))
