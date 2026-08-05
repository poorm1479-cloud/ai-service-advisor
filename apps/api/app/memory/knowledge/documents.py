"""Business knowledge documents."""

from __future__ import annotations

from uuid import UUID

from app.memory.core.store import KnowledgeBaseStorePort, KnowledgeDocument


class KnowledgeDocumentService:
    def __init__(self, kb: KnowledgeBaseStorePort) -> None:
        self._kb = kb

    async def upsert(
        self,
        shop_id: UUID,
        *,
        title: str,
        content: str,
        tags: list[str] | None = None,
        doc_id: UUID | None = None,
        summary: str | None = None,
        source: str = "workflow",
    ) -> KnowledgeDocument:
        if doc_id is not None:
            existing = await self._kb.get_document(shop_id, doc_id)
            if existing is not None:
                existing.title = title
                existing.content = content
                existing.summary = summary
                existing.tags = list(tags or existing.tags)
                existing.source = source
                return await self._kb.upsert_document(existing)
        doc = KnowledgeDocument.create(
            shop_id=shop_id,
            title=title,
            content=content,
            summary=summary,
            tags=tags,
            source=source,
            doc_id=doc_id,
        )
        return await self._kb.upsert_document(doc)

    async def list(
        self, shop_id: UUID, *, limit: int = 100, tags: list[str] | None = None
    ) -> list[KnowledgeDocument]:
        return await self._kb.list_documents(shop_id, limit=limit, tags=tags)
