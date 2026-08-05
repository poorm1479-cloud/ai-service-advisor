"""Connection authentication helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.mcp_hub.adapters import get_adapter
from app.mcp_hub.enums import AuthMethod, ConnectionStatus
from app.mcp_hub.models import ConnectionCredentials, IntegrationConnection


class ConnectionAuthenticator:
    """Validates and exchanges credentials via the provider adapter."""

    async def authenticate(
        self,
        connection: IntegrationConnection,
        *,
        fields: dict[str, str] | None = None,
        scopes: list[str] | None = None,
        method: AuthMethod | None = None,
    ) -> IntegrationConnection:
        adapter = get_adapter(connection.provider)
        creds = connection.credentials or ConnectionCredentials(
            method=method or adapter.manifest().auth_method
        )
        if fields:
            creds.fields.update(fields)
        if scopes is not None:
            creds.scopes = list(scopes)
        if method is not None:
            creds.method = method

        connection.status = ConnectionStatus.CONNECTING
        try:
            connection.credentials = await adapter.authenticate(creds)
            connection.status = ConnectionStatus.CONNECTED
            connection.connected_at = datetime.now(timezone.utc)
            connection.last_error = None
            connection.api_version = connection.api_version or adapter.manifest().api_version
            if not connection.permissions:
                connection.permissions = list(adapter.manifest().required_scopes)
        except Exception as exc:
            connection.status = ConnectionStatus.ERROR
            connection.last_error = str(exc)
            raise
        return connection
