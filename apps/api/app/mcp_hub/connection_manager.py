"""Connection lifecycle manager."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.mcp_hub.adapters import get_adapter, list_adapters
from app.mcp_hub.auth import ConnectionAuthenticator
from app.mcp_hub.enums import ConnectionStatus, IntegrationProvider, LogLevel
from app.mcp_hub.logging import IntegrationLogger
from app.mcp_hub.models import IntegrationConnection, IntegrationManifest
from app.mcp_hub.monitoring import McpHubMonitor
from app.mcp_hub.store import McpHubStorePort
from app.mcp_hub.versioning import VersionService


class ConnectionManager:
    def __init__(
        self,
        store: McpHubStorePort,
        *,
        authenticator: ConnectionAuthenticator | None = None,
        logger: IntegrationLogger | None = None,
        versions: VersionService | None = None,
        monitor: McpHubMonitor | None = None,
    ) -> None:
        self._store = store
        self._auth = authenticator or ConnectionAuthenticator()
        self._logger = logger or IntegrationLogger(store)
        self._versions = versions or VersionService()
        self._monitor = monitor or McpHubMonitor()

    def list_integrations(self) -> list[IntegrationManifest]:
        return [a.manifest() for a in list_adapters()]

    def create(
        self,
        shop_id: UUID,
        *,
        provider: IntegrationProvider,
        name: str | None = None,
        api_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationConnection:
        adapter = get_adapter(provider)
        version = self._versions.resolve(provider, api_version)
        conn = IntegrationConnection(
            id=uuid4(),
            shop_id=shop_id,
            provider=provider,
            name=name or adapter.manifest().display_name,
            status=ConnectionStatus.DISCONNECTED,
            api_version=version,
            metadata=metadata or {},
        )
        saved = self._store.save_connection(conn)
        self._monitor.record_created(provider.value)
        self._logger.log(
            shop_id,
            event="connection.created",
            message=f"Created {provider.value} connection",
            provider=provider,
            connection_id=saved.id,
        )
        return saved

    def get(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection | None:
        return self._store.get_connection(shop_id, connection_id)

    def list(self, shop_id: UUID, *, provider: IntegrationProvider | None = None) -> list[IntegrationConnection]:
        return self._store.list_connections(shop_id, provider=provider)

    async def connect(
        self,
        shop_id: UUID,
        connection_id: UUID,
        *,
        fields: dict[str, str] | None = None,
        scopes: list[str] | None = None,
        demo: bool = False,
    ) -> IntegrationConnection:
        conn = self._require(shop_id, connection_id)
        creds = dict(fields or {})
        if demo:
            creds.setdefault("demo", "true")
        try:
            conn = await self._auth.authenticate(conn, fields=creds, scopes=scopes)
        except Exception as exc:
            self._store.save_connection(conn)
            self._logger.log(
                shop_id,
                event="connection.auth_failed",
                message=str(exc),
                level=LogLevel.ERROR,
                provider=conn.provider,
                connection_id=conn.id,
            )
            raise
        saved = self._store.save_connection(conn)
        self._monitor.record_connected()
        self._logger.log(
            shop_id,
            event="connection.connected",
            message=f"Connected {conn.provider.value}",
            provider=conn.provider,
            connection_id=conn.id,
        )
        return saved

    async def disconnect(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection:
        conn = self._require(shop_id, connection_id)
        conn.status = ConnectionStatus.DISCONNECTED
        conn.connected_at = None
        if conn.credentials:
            conn.credentials.access_token = None
            conn.credentials.refresh_token = None
        saved = self._store.save_connection(conn)
        self._monitor.record_disconnected()
        self._logger.log(
            shop_id,
            event="connection.disconnected",
            message=f"Disconnected {conn.provider.value}",
            provider=conn.provider,
            connection_id=conn.id,
        )
        return saved

    async def test(self, shop_id: UUID, connection_id: UUID) -> dict[str, Any]:
        conn = self._require(shop_id, connection_id)
        adapter = get_adapter(conn.provider)
        result = await adapter.test_connection(conn)
        conn.last_tested_at = datetime.now(timezone.utc)
        if not result.get("ok"):
            conn.status = ConnectionStatus.ERROR
            conn.last_error = str(result.get("error") or "test failed")
        elif conn.status == ConnectionStatus.ERROR:
            conn.status = ConnectionStatus.CONNECTED
            conn.last_error = None
        self._store.save_connection(conn)
        self._monitor.record_test()
        self._logger.log(
            shop_id,
            event="connection.tested",
            message="Connection test completed",
            provider=conn.provider,
            connection_id=conn.id,
            details=result,
        )
        return result

    def delete(self, shop_id: UUID, connection_id: UUID) -> bool:
        ok = self._store.delete_connection(shop_id, connection_id)
        if ok:
            self._logger.log(
                shop_id,
                event="connection.deleted",
                message="Connection deleted",
                connection_id=connection_id,
            )
        return ok

    def _require(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection:
        conn = self._store.get_connection(shop_id, connection_id)
        if conn is None:
            raise KeyError(f"Connection not found: {connection_id}")
        return conn
