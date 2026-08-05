"""Phase 19 knowledge / shop-profile store (in-memory + port).

Does not replace Phase 15 ``MemoryStorePort`` / ``ai_memories``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class KnowledgeDocument:
    id: UUID
    shop_id: UUID
    title: str
    content: str
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        *,
        shop_id: UUID,
        title: str,
        content: str,
        summary: str | None = None,
        tags: list[str] | None = None,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
        doc_id: UUID | None = None,
    ) -> KnowledgeDocument:
        return cls(
            id=doc_id or uuid4(),
            shop_id=shop_id,
            title=title,
            content=content,
            summary=summary,
            tags=list(tags or []),
            source=source,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "shop_id": str(self.shop_id),
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "tags": list(self.tags),
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ShopProfileRecord:
    shop_id: UUID
    display_name: str = ""
    timezone: str = "America/Los_Angeles"
    specialties: list[str] = field(default_factory=list)
    hours: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shop_id": str(self.shop_id),
            "display_name": self.display_name,
            "timezone": self.timezone,
            "specialties": list(self.specialties),
            "hours": dict(self.hours),
            "preferences": dict(self.preferences),
            "metadata": dict(self.metadata),
        }


class KnowledgeBaseStorePort(Protocol):
    async def upsert_document(self, doc: KnowledgeDocument) -> KnowledgeDocument: ...

    async def get_document(self, shop_id: UUID, doc_id: UUID) -> KnowledgeDocument | None: ...

    async def list_documents(
        self, shop_id: UUID, *, limit: int = 100, tags: list[str] | None = None
    ) -> list[KnowledgeDocument]: ...

    async def search_documents(
        self, shop_id: UUID, *, text: str, limit: int = 12
    ) -> list[KnowledgeDocument]: ...

    async def delete_document(self, shop_id: UUID, doc_id: UUID) -> bool: ...

    async def get_shop_profile(self, shop_id: UUID) -> ShopProfileRecord: ...

    async def save_shop_profile(self, profile: ShopProfileRecord) -> ShopProfileRecord: ...


class InMemoryKnowledgeBaseStore:
    """Tenant-isolated in-memory knowledge + shop profile store."""

    def __init__(self) -> None:
        self._docs: dict[UUID, KnowledgeDocument] = {}
        self._profiles: dict[UUID, ShopProfileRecord] = {}

    async def upsert_document(self, doc: KnowledgeDocument) -> KnowledgeDocument:
        existing = self._docs.get(doc.id)
        if existing is not None and existing.shop_id != doc.shop_id:
            raise PermissionError("Cross-shop knowledge document write blocked")
        doc.updated_at = _utcnow()
        self._docs[doc.id] = doc
        return doc

    async def get_document(self, shop_id: UUID, doc_id: UUID) -> KnowledgeDocument | None:
        doc = self._docs.get(doc_id)
        if doc is None or doc.shop_id != shop_id:
            return None
        return doc

    async def list_documents(
        self, shop_id: UUID, *, limit: int = 100, tags: list[str] | None = None
    ) -> list[KnowledgeDocument]:
        items = [d for d in self._docs.values() if d.shop_id == shop_id]
        if tags:
            tagset = set(tags)
            items = [d for d in items if tagset.intersection(d.tags)]
        items.sort(key=lambda d: d.updated_at, reverse=True)
        return items[:limit]

    async def search_documents(
        self, shop_id: UUID, *, text: str, limit: int = 12
    ) -> list[KnowledgeDocument]:
        q = (text or "").strip().lower()
        items = await self.list_documents(shop_id, limit=500)
        if not q:
            return items[:limit]
        scored: list[tuple[int, KnowledgeDocument]] = []
        for doc in items:
            blob = f"{doc.title} {doc.content} {doc.summary or ''} {' '.join(doc.tags)}".lower()
            score = blob.count(q) + (3 if q in doc.title.lower() else 0)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:limit]]

    async def delete_document(self, shop_id: UUID, doc_id: UUID) -> bool:
        doc = self._docs.get(doc_id)
        if doc is None or doc.shop_id != shop_id:
            return False
        del self._docs[doc_id]
        return True

    async def get_shop_profile(self, shop_id: UUID) -> ShopProfileRecord:
        profile = self._profiles.get(shop_id)
        if profile is None:
            profile = ShopProfileRecord(shop_id=shop_id)
            self._profiles[shop_id] = profile
        return profile

    async def save_shop_profile(self, profile: ShopProfileRecord) -> ShopProfileRecord:
        profile.updated_at = _utcnow()
        self._profiles[profile.shop_id] = profile
        return profile
