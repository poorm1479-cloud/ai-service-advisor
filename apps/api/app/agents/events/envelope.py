"""Event envelope wrapping typed payloads for bus transport."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

T = TypeVar("T")


@dataclass(slots=True)
class EventEnvelope(Generic[T]):
    """Transport wrapper for agent events (MCP-ready metadata)."""

    event_type: str
    payload: T
    shop_id: UUID
    correlation_id: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    source_agent: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "shop_id": str(self.shop_id),
            "correlation_id": self.correlation_id,
            "source_agent": self.source_agent,
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": self.metadata,
            "payload": self.payload,
        }
