"""Phase 19 Knowledge Base / Shop Memory — core interfaces."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryBundle, MemoryQuery, MemoryRecord, RememberRequest


class MemoryManagerPort(Protocol):
    """Unified read/write façade — write path intended for Workflow / Memory Plugin only."""

    async def save_memory(self, request: RememberRequest) -> MemoryRecord: ...

    async def search_memory(self, query: MemoryQuery) -> MemoryBundle: ...

    async def get_customer_history(
        self, shop_id: UUID, customer_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]: ...

    async def get_vehicle_history(
        self, shop_id: UUID, vehicle_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]: ...

    async def get_shop_preference(self, shop_id: UUID) -> dict[str, Any]: ...

    async def retrieve_knowledge(
        self, shop_id: UUID, *, query: str | None = None, limit: int = 12
    ) -> list[dict[str, Any]]: ...

    async def update_customer_profile(
        self, shop_id: UUID, customer_id: UUID, patch: dict[str, Any]
    ) -> MemoryRecord: ...

    async def update_vehicle_health(
        self, shop_id: UUID, vehicle_id: UUID, health: dict[str, Any]
    ) -> MemoryRecord: ...


class KnowledgeStorePort(Protocol):
    async def upsert_document(self, doc: Any) -> Any: ...

    async def get_document(self, shop_id: UUID, doc_id: UUID) -> Any | None: ...

    async def list_documents(
        self, shop_id: UUID, *, limit: int = 100, tags: list[str] | None = None
    ) -> list[Any]: ...

    async def search_documents(
        self, shop_id: UUID, *, text: str, limit: int = 12
    ) -> list[Any]: ...

    async def delete_document(self, shop_id: UUID, doc_id: UUID) -> bool: ...


class ShopMemoryPort(Protocol):
    async def get_profile(self, shop_id: UUID) -> dict[str, Any]: ...

    async def get_preferences(self, shop_id: UUID) -> dict[str, Any]: ...

    async def save_preference(
        self, shop_id: UUID, key: str, value: Any, *, rationale: str = ""
    ) -> MemoryRecord: ...


class CustomerMemoryPort(Protocol):
    async def history(self, shop_id: UUID, customer_id: UUID, *, limit: int = 50) -> list[MemoryRecord]: ...

    async def preferences(self, shop_id: UUID, customer_id: UUID) -> dict[str, Any]: ...

    async def update_profile(
        self, shop_id: UUID, customer_id: UUID, patch: dict[str, Any]
    ) -> MemoryRecord: ...


class VehicleMemoryPort(Protocol):
    async def history(self, shop_id: UUID, vehicle_id: UUID, *, limit: int = 50) -> list[MemoryRecord]: ...

    async def health(self, shop_id: UUID, vehicle_id: UUID) -> dict[str, Any]: ...

    async def update_health(
        self, shop_id: UUID, vehicle_id: UUID, health: dict[str, Any]
    ) -> MemoryRecord: ...
