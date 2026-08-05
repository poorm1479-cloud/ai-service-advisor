"""Long-term memory domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.memory.enums import MemoryCategory, MemorySource, MemoryType


@dataclass(slots=True)
class MemoryRecord:
    id: UUID
    shop_id: UUID
    memory_type: MemoryType
    category: MemoryCategory
    content: str
    summary: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    conversation_id: UUID | None = None
    importance: float = 0.5
    confidence: float = 1.0
    embedding: list[float] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: MemorySource = MemorySource.SYSTEM
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0

    def __post_init__(self) -> None:
        if self.id is None:  # type: ignore[unreachable]
            self.id = uuid4()


@dataclass(slots=True)
class MemoryHit:
    record: MemoryRecord
    score: float
    reason: str = "relevance"


@dataclass(slots=True)
class MemoryQuery:
    shop_id: UUID
    text: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    memory_types: list[MemoryType] | None = None
    categories: list[MemoryCategory] | None = None
    limit: int = 12
    min_score: float = 0.05


@dataclass(slots=True)
class MemoryBundle:
    """Auto-loaded context injected into AgentContext for AI use."""

    shop_id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    hits: list[MemoryHit] = field(default_factory=list)
    by_category: dict[str, list[str]] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    communication_style: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shop_id": str(self.shop_id),
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "vehicle_id": str(self.vehicle_id) if self.vehicle_id else None,
            "hit_count": len(self.hits),
            "by_category": self.by_category,
            "preferences": self.preferences,
            "communication_style": self.communication_style,
            "prompt": self.prompt,
            "memories": [
                {
                    "id": str(h.record.id),
                    "type": h.record.memory_type.value,
                    "category": h.record.category.value,
                    "content": h.record.content,
                    "score": round(h.score, 4),
                    "reason": h.reason,
                }
                for h in self.hits
            ],
        }


@dataclass(slots=True)
class RememberRequest:
    shop_id: UUID
    content: str
    memory_type: MemoryType
    category: MemoryCategory
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    conversation_id: UUID | None = None
    importance: float = 0.5
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: MemorySource = MemorySource.MANUAL
    summary: str | None = None
