"""CRM agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class TimelineEntry:
    id: UUID
    kind: str
    summary: str
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CrmUpdateRequest:
    customer_id: UUID | None
    channel: str | None = None
    message: str | None = None
    intent: str | None = None
    vehicle_id: UUID | None = None
    repair_note: str | None = None


@dataclass(slots=True)
class CrmUpdateResult:
    customer_id: UUID | None
    communication_recorded: bool = False
    repair_updated: bool = False
    timeline_entries: list[TimelineEntry] = field(default_factory=list)
    customer_summary: str | None = None
    # AI Decision Layer — proposed CRM writes; Workflow executes them
    decision: Any | None = None
