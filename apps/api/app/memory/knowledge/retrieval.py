"""Knowledge retrieval — AI-readable, shop-scoped."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.core.store import KnowledgeBaseStorePort
from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryQuery
from app.memory.service import LongTermMemoryService


class KnowledgeRetrievalService:
    def __init__(self, kb: KnowledgeBaseStorePort, ltm: LongTermMemoryService) -> None:
        self._kb = kb
        self._ltm = ltm

    async def retrieve(
        self, shop_id: UUID, *, query: str | None = None, limit: int = 12
    ) -> list[dict[str, Any]]:
        text = (query or "").strip()
        docs = await self._kb.search_documents(shop_id, text=text or " ", limit=limit)
        if text == "":
            docs = await self._kb.list_documents(shop_id, limit=limit)
        out = [
            {
                "kind": "document",
                **d.to_dict(),
            }
            for d in docs
        ]
        # Also pull business knowledge memories
        bundle = self._ltm.retrieve(
            MemoryQuery(
                shop_id=shop_id,
                text=text or None,
                memory_types=[MemoryType.KNOWLEDGE, MemoryType.BUSINESS],
                categories=[MemoryCategory.BUSINESS_KNOWLEDGE],
                limit=limit,
            )
        )
        for hit in bundle.hits:
            out.append(
                {
                    "kind": "memory",
                    "id": str(hit.record.id),
                    "shop_id": str(hit.record.shop_id),
                    "title": hit.record.summary or hit.record.category.value,
                    "content": hit.record.content,
                    "score": hit.score,
                    "tags": list(hit.record.tags),
                }
            )
        return out[:limit]
