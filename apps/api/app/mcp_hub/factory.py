"""DI factory for MCP Integration Hub."""

from __future__ import annotations

from dataclasses import dataclass

from app.mcp_hub.auth import ConnectionAuthenticator
from app.mcp_hub.connection_manager import ConnectionManager
from app.mcp_hub.logging import IntegrationLogger
from app.mcp_hub.models import RetryPolicy
from app.mcp_hub.monitoring import McpHubMonitor
from app.mcp_hub.permissions import PermissionService
from app.mcp_hub.service import McpHubService
from app.mcp_hub.store import InMemoryMcpHubStore, McpHubStorePort
from app.mcp_hub.versioning import VersionService


@dataclass(slots=True)
class McpHubRuntime:
    service: McpHubService
    store: McpHubStorePort
    connections: ConnectionManager
    permissions: PermissionService
    logger: IntegrationLogger
    versions: VersionService
    monitor: McpHubMonitor


_runtime: McpHubRuntime | None = None


def build_mcp_hub_runtime(
    *,
    store: McpHubStorePort | None = None,
    retry_policy: RetryPolicy | None = None,
) -> McpHubRuntime:
    resource_store = store or InMemoryMcpHubStore()
    monitor = McpHubMonitor()
    logger = IntegrationLogger(resource_store)
    versions = VersionService()
    permissions = PermissionService(resource_store)
    authenticator = ConnectionAuthenticator()
    connections = ConnectionManager(
        resource_store,
        authenticator=authenticator,
        logger=logger,
        versions=versions,
        monitor=monitor,
    )
    service = McpHubService(
        resource_store,
        connections=connections,
        permissions=permissions,
        logger=logger,
        versions=versions,
        monitor=monitor,
        retry_policy=retry_policy,
    )
    return McpHubRuntime(
        service=service,
        store=resource_store,
        connections=connections,
        permissions=permissions,
        logger=logger,
        versions=versions,
        monitor=monitor,
    )


def get_mcp_hub_runtime() -> McpHubRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_mcp_hub_runtime()
    return _runtime


def reset_mcp_hub_runtime() -> None:
    global _runtime
    from app.mcp_hub.adapters import reset_adapter_registry

    _runtime = None
    reset_adapter_registry()
