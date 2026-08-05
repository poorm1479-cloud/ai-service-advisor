"""In-memory integration connection store (tenant-scoped)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.integrations.enums import IntegrationProvider
from app.integrations.models import IntegrationConnection
from app.integrations.security import TenantIsolationError, assert_same_tenant


class IntegrationStorePort(Protocol):
    async def save(self, connection: IntegrationConnection) -> IntegrationConnection: ...

    async def get(
        self, shop_id: UUID, connection_id: UUID
    ) -> IntegrationConnection | None: ...

    async def get_by_provider(
        self, shop_id: UUID, provider: IntegrationProvider
    ) -> IntegrationConnection | None: ...

    async def list_for_shop(self, shop_id: UUID) -> list[IntegrationConnection]: ...

    async def delete(self, shop_id: UUID, connection_id: UUID) -> bool: ...


class InMemoryIntegrationStore:
    def __init__(self) -> None:
        self._items: dict[UUID, IntegrationConnection] = {}

    async def save(self, connection: IntegrationConnection) -> IntegrationConnection:
        self._items[connection.id] = connection
        return connection

    async def get(self, shop_id: UUID, connection_id: UUID) -> IntegrationConnection | None:
        conn = self._items.get(connection_id)
        if conn is None:
            return None
        if conn.shop_id != shop_id:
            raise TenantIsolationError("Cross-shop connection access denied")
        return conn

    async def get_by_provider(
        self, shop_id: UUID, provider: IntegrationProvider
    ) -> IntegrationConnection | None:
        for conn in self._items.values():
            if conn.shop_id == shop_id and conn.provider == provider:
                return conn
        return None

    async def list_for_shop(self, shop_id: UUID) -> list[IntegrationConnection]:
        return [c for c in self._items.values() if c.shop_id == shop_id]

    async def delete(self, shop_id: UUID, connection_id: UUID) -> bool:
        conn = self._items.get(connection_id)
        if conn is None:
            return False
        assert_same_tenant(expected_shop_id=shop_id, actual_shop_id=conn.shop_id)
        del self._items[connection_id]
        return True
