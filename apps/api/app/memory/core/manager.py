"""MemoryManager — orchestrates Shop / Customer / Vehicle / Knowledge domains.

Write APIs are for Workflow → Memory Plugin only. AI agents must propose
Decision Objects; they must not call save/update methods directly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.core.store import (
    InMemoryKnowledgeBaseStore,
    KnowledgeBaseStorePort,
    KnowledgeDocument,
)
from app.memory.customer.history import CustomerHistoryService
from app.memory.customer.preferences import CustomerPreferenceService
from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.knowledge.documents import KnowledgeDocumentService
from app.memory.knowledge.retrieval import KnowledgeRetrievalService
from app.memory.models import MemoryBundle, MemoryQuery, MemoryRecord, RememberRequest
from app.memory.service import LongTermMemoryService
from app.memory.shop.preferences import ShopPreferenceService
from app.memory.shop.profile import ShopProfileService
from app.memory.vehicle.health import VehicleHealthService
from app.memory.vehicle.history import VehicleHistoryService


class MemoryManager:
    """Phase 19 unified Knowledge Base + Shop Memory manager."""

    def __init__(
        self,
        *,
        long_term: LongTermMemoryService,
        kb_store: KnowledgeBaseStorePort | None = None,
    ) -> None:
        self._ltm = long_term
        self._kb = kb_store or InMemoryKnowledgeBaseStore()
        self.shop_profile = ShopProfileService(self._kb, self._ltm)
        self.shop_preferences = ShopPreferenceService(self._kb, self._ltm)
        self.customer_history = CustomerHistoryService(self._ltm)
        self.customer_preferences = CustomerPreferenceService(self._ltm)
        self.vehicle_history = VehicleHistoryService(self._ltm)
        self.vehicle_health = VehicleHealthService(self._ltm)
        self.documents = KnowledgeDocumentService(self._kb)
        self.retrieval = KnowledgeRetrievalService(self._kb, self._ltm)

    @property
    def long_term(self) -> LongTermMemoryService:
        return self._ltm

    @property
    def knowledge_store(self) -> KnowledgeBaseStorePort:
        return self._kb

    # --- Capabilities (async for plugin parity) ---

    async def save_memory(self, request: RememberRequest) -> MemoryRecord:
        return self._ltm.remember(request)

    async def search_memory(self, query: MemoryQuery) -> MemoryBundle:
        return self._ltm.retrieve(query)

    async def get_customer_history(
        self, shop_id: UUID, customer_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]:
        return await self.customer_history.list_history(shop_id, customer_id, limit=limit)

    async def get_vehicle_history(
        self, shop_id: UUID, vehicle_id: UUID, *, limit: int = 50
    ) -> list[MemoryRecord]:
        return await self.vehicle_history.list_history(shop_id, vehicle_id, limit=limit)

    async def get_shop_preference(self, shop_id: UUID) -> dict[str, Any]:
        return await self.shop_preferences.get_all(shop_id)

    async def retrieve_knowledge(
        self, shop_id: UUID, *, query: str | None = None, limit: int = 12
    ) -> list[dict[str, Any]]:
        return await self.retrieval.retrieve(shop_id, query=query, limit=limit)

    async def update_customer_profile(
        self, shop_id: UUID, customer_id: UUID, patch: dict[str, Any]
    ) -> MemoryRecord:
        return await self.customer_preferences.update_profile(shop_id, customer_id, patch)

    async def update_vehicle_health(
        self, shop_id: UUID, vehicle_id: UUID, health: dict[str, Any]
    ) -> MemoryRecord:
        return await self.vehicle_health.update(shop_id, vehicle_id, health)

    async def apply_shop_preference_decision(
        self, shop_id: UUID, *, preferences: dict[str, Any], rationale: str = ""
    ) -> list[MemoryRecord]:
        return await self.shop_preferences.apply_patch(
            shop_id, preferences, rationale=rationale
        )

    async def upsert_knowledge_document(
        self,
        shop_id: UUID,
        *,
        title: str,
        content: str,
        tags: list[str] | None = None,
        doc_id: UUID | None = None,
        summary: str | None = None,
    ) -> KnowledgeDocument:
        return await self.documents.upsert(
            shop_id,
            title=title,
            content=content,
            tags=tags,
            doc_id=doc_id,
            summary=summary,
        )

    def write_facts(self, shop_id: UUID, facts: list[dict[str, Any]]) -> list[MemoryRecord]:
        """Legacy MemoryDecision helper — Workflow-only write path."""
        out: list[MemoryRecord] = []
        for fact in facts:
            content = str(fact.get("content") or fact.get("text") or "").strip()
            if not content:
                continue
            mem_type = fact.get("memory_type") or MemoryType.SEMANTIC.value
            category = fact.get("category") or MemoryCategory.GENERAL.value
            try:
                mt = MemoryType(str(mem_type))
            except ValueError:
                mt = MemoryType.SEMANTIC
            try:
                cat = MemoryCategory(str(category))
            except ValueError:
                cat = MemoryCategory.GENERAL
            out.append(
                self._ltm.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=content,
                        summary=fact.get("summary"),
                        memory_type=mt,
                        category=cat,
                        customer_id=_as_uuid(fact.get("customer_id")),
                        vehicle_id=_as_uuid(fact.get("vehicle_id")),
                        importance=float(fact.get("importance") or 0.6),
                        confidence=float(fact.get("confidence") or 1.0),
                        tags=list(fact.get("tags") or ["decision"]),
                        metadata=dict(fact.get("metadata") or {}),
                        source=MemorySource.WORKFLOW,
                    )
                )
            )
        return out


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None
