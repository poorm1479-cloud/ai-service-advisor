"""MCP Integration Hub service — agent-facing invoke + hub admin."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.mcp_hub.adapters import get_adapter, list_adapters
from app.mcp_hub.connection_manager import ConnectionManager
from app.mcp_hub.enums import (
    ConnectionStatus,
    IntegrationProvider,
    InvokeStatus,
    LogLevel,
    PermissionAction,
)
from app.mcp_hub.logging import IntegrationLogger
from app.mcp_hub.models import (
    IntegrationConnection,
    IntegrationLogEntry,
    IntegrationManifest,
    InvokeRequest,
    InvokeResult,
    McpToolDescriptor,
    PermissionGrant,
    RetryPolicy,
)
from app.mcp_hub.monitoring import McpHubMonitor
from app.mcp_hub.permissions import PermissionDenied, PermissionService
from app.mcp_hub.retry import RetryExecutor
from app.mcp_hub.store import McpHubStorePort
from app.mcp_hub.versioning import VersionService


class McpHubService:
    def __init__(
        self,
        store: McpHubStorePort,
        *,
        connections: ConnectionManager,
        permissions: PermissionService,
        logger: IntegrationLogger,
        versions: VersionService,
        monitor: McpHubMonitor,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._store = store
        self.connections = connections
        self.permissions = permissions
        self.logger = logger
        self.versions = versions
        self.monitor = monitor
        self._retry = RetryExecutor(retry_policy or RetryPolicy(), monitor=monitor)

    def list_integrations(self) -> list[IntegrationManifest]:
        return self.connections.list_integrations()

    def list_mcp_tools(self, *, provider: IntegrationProvider | None = None) -> list[McpToolDescriptor]:
        tools: list[McpToolDescriptor] = []
        for adapter in list_adapters():
            if provider is not None and adapter.provider != provider:
                continue
            tools.extend(adapter.tools())
        return tools

    def list_mcp_descriptors(self, *, provider: IntegrationProvider | None = None) -> list[dict[str, Any]]:
        return [t.to_mcp() for t in self.list_mcp_tools(provider=provider)]

    async def create_connection(
        self,
        shop_id: UUID,
        *,
        provider: IntegrationProvider,
        name: str | None = None,
        api_version: str | None = None,
        credentials: dict[str, str] | None = None,
        connect: bool = False,
        demo: bool = True,
    ) -> IntegrationConnection:
        self.permissions.ensure_defaults(shop_id)
        conn = self.connections.create(
            shop_id,
            provider=provider,
            name=name,
            api_version=api_version,
        )
        if connect or credentials or demo:
            conn = await self.connections.connect(
                shop_id,
                conn.id,
                fields=credentials,
                demo=demo if not credentials else False,
            )
        return conn

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        started = time.perf_counter()
        self.permissions.ensure_defaults(request.shop_id)

        try:
            self.permissions.check(
                request.shop_id,
                principal=request.principal,
                provider=request.provider,
                action=PermissionAction.INVOKE,
            )
        except PermissionDenied as exc:
            self.monitor.record_denied()
            self.logger.log(
                request.shop_id,
                event="invoke.denied",
                message=str(exc),
                level=LogLevel.WARNING,
                provider=request.provider,
                connection_id=request.connection_id,
            )
            result = InvokeResult(
                id=uuid4(),
                shop_id=request.shop_id,
                provider=request.provider,
                connection_id=request.connection_id,
                tool=request.tool,
                status=InvokeStatus.DENIED,
                attempts=0,
                error=str(exc),
                api_version=request.api_version or self.versions.default_version(request.provider),
                duration_ms=int((time.perf_counter() - started) * 1000),
                created_at=datetime.now(timezone.utc),
            )
            return self._store.save_invoke(result)

        connection = self._resolve_connection(request)
        api_version = self.versions.resolve(request.provider, request.api_version or connection.api_version)
        connection.api_version = api_version
        adapter = get_adapter(request.provider)

        async def _call() -> dict[str, Any]:
            return await adapter.invoke(connection, request)

        try:
            data, attempts = await self._retry.run(_call)
            status = InvokeStatus.SUCCESS
            error = None
            self.monitor.record_invoke(request.provider.value, ok=True)
            self.logger.log(
                request.shop_id,
                event="invoke.success",
                message=f"Invoked {request.tool}",
                provider=request.provider,
                connection_id=connection.id,
                details={"tool": request.tool, "attempts": attempts},
            )
        except Exception as exc:
            data = {}
            attempts = self._retry.policy.max_attempts
            status = InvokeStatus.FAILED
            error = str(exc)
            self.monitor.record_invoke(request.provider.value, ok=False)
            self.logger.log(
                request.shop_id,
                event="invoke.failed",
                message=error,
                level=LogLevel.ERROR,
                provider=request.provider,
                connection_id=connection.id,
                details={"tool": request.tool},
            )

        result = InvokeResult(
            id=uuid4(),
            shop_id=request.shop_id,
            provider=request.provider,
            connection_id=connection.id,
            tool=request.tool,
            status=status,
            attempts=attempts,
            data=data,
            error=error,
            api_version=api_version,
            duration_ms=int((time.perf_counter() - started) * 1000),
            created_at=datetime.now(timezone.utc),
        )
        return self._store.save_invoke(result)

    def list_logs(
        self,
        shop_id: UUID,
        *,
        limit: int = 100,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationLogEntry]:
        return self.logger.list_logs(shop_id, limit=limit, provider=provider)

    def list_invokes(self, shop_id: UUID, *, limit: int = 50) -> list[InvokeResult]:
        return self._store.list_invokes(shop_id, limit=limit)

    def list_permissions(self, shop_id: UUID) -> list[PermissionGrant]:
        self.permissions.ensure_defaults(shop_id)
        return self._store.list_permissions(shop_id)

    def grant_permission(
        self,
        shop_id: UUID,
        *,
        principal: str,
        provider: IntegrationProvider,
        actions: list[PermissionAction],
        scopes: list[str] | None = None,
    ) -> PermissionGrant:
        return self.permissions.grant(
            shop_id,
            principal=principal,
            provider=provider,
            actions=actions,
            scopes=scopes,
        )

    def metrics(self) -> dict[str, object]:
        return self.monitor.snapshot()

    def version_matrix(self) -> dict[str, list[str]]:
        return {p.value: self.versions.supported(p) for p in IntegrationProvider}

    def _resolve_connection(self, request: InvokeRequest) -> IntegrationConnection:
        if request.connection_id is not None:
            conn = self.connections.get(request.shop_id, request.connection_id)
            if conn is None:
                raise KeyError(f"Connection not found: {request.connection_id}")
            if conn.provider != request.provider:
                raise ValueError("Connection provider mismatch")
            if conn.status != ConnectionStatus.CONNECTED:
                raise ValueError(f"Connection is {conn.status.value}; connect first")
            return conn

        connected = [
            c
            for c in self.connections.list(request.shop_id, provider=request.provider)
            if c.status == ConnectionStatus.CONNECTED
        ]
        if not connected:
            raise ValueError(f"No connected {request.provider.value} connection; create and connect one first")
        return connected[0]
