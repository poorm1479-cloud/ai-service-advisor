"""Structured integration logging."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.mcp_hub.enums import IntegrationProvider, LogLevel
from app.mcp_hub.models import IntegrationLogEntry
from app.mcp_hub.store import McpHubStorePort


class IntegrationLogger:
    def __init__(self, store: McpHubStorePort) -> None:
        self._store = store

    def log(
        self,
        shop_id: UUID,
        *,
        event: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        provider: IntegrationProvider | None = None,
        connection_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> IntegrationLogEntry:
        entry = IntegrationLogEntry(
            id=uuid4(),
            shop_id=shop_id,
            provider=provider,
            connection_id=connection_id,
            level=level,
            event=event,
            message=message,
            details=details or {},
            created_at=datetime.now(timezone.utc),
        )
        return self._store.append_log(entry)

    def list_logs(
        self,
        shop_id: UUID,
        *,
        limit: int = 100,
        provider: IntegrationProvider | None = None,
    ) -> list[IntegrationLogEntry]:
        return self._store.list_logs(shop_id, limit=limit, provider=provider)
