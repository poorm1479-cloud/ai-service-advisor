"""Write / upsert long-term memories."""

from __future__ import annotations

from uuid import uuid4

from app.memory.embeddings import embed
from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryRecord, RememberRequest
from app.memory.monitoring import MemoryMonitor
from app.memory.store import MemoryStorePort


class MemoryIndexer:
    def __init__(self, store: MemoryStorePort, monitor: MemoryMonitor | None = None) -> None:
        self._store = store
        self._monitor = monitor or MemoryMonitor()

    def remember(self, request: RememberRequest) -> MemoryRecord:
        # Deduplicate near-identical content for same customer+category
        existing = self._store.list(
            request.shop_id,
            customer_id=request.customer_id,
            category=request.category,
            limit=50,
        )
        for row in existing:
            if row.content.strip().lower() == request.content.strip().lower():
                row.importance = max(row.importance, request.importance)
                row.confidence = max(row.confidence, request.confidence)
                row.metadata.update(request.metadata)
                if request.tags:
                    row.tags = sorted(set(row.tags) | set(request.tags))
                row.embedding = embed(row.content)
                saved = self._store.save(row)
                self._monitor.record_remember(saved.memory_type.value, saved.category.value)
                return saved

        record = MemoryRecord(
            id=uuid4(),
            shop_id=request.shop_id,
            memory_type=request.memory_type,
            category=request.category,
            content=request.content.strip(),
            summary=request.summary,
            customer_id=request.customer_id,
            vehicle_id=request.vehicle_id,
            conversation_id=request.conversation_id,
            importance=request.importance,
            confidence=request.confidence,
            embedding=embed(request.content),
            tags=list(request.tags),
            metadata=dict(request.metadata),
            source=request.source,
        )
        saved = self._store.save(record)
        self._monitor.record_remember(saved.memory_type.value, saved.category.value)
        return saved

    def remember_fact(
        self,
        shop_id,
        content: str,
        *,
        memory_type: MemoryType,
        category: MemoryCategory,
        customer_id=None,
        vehicle_id=None,
        importance: float = 0.6,
        tags: list[str] | None = None,
        source=None,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        from app.memory.enums import MemorySource

        return self.remember(
            RememberRequest(
                shop_id=shop_id,
                content=content,
                memory_type=memory_type,
                category=category,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                importance=importance,
                tags=tags or [],
                source=source or MemorySource.SYSTEM,
                metadata=metadata or {},
            )
        )
