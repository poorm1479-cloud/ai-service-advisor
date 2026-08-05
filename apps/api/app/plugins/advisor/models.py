"""Advisor context — read-only inputs for decide-only AI Service Advisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class AdvisorContext:
    """Bundle of customer service lifecycle context (read-only for AI)."""

    shop_id: UUID
    conversation_id: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    channel: str | None = None
    inbound_text: str | None = None
    intent: str | None = None
    customer: dict[str, Any] | None = None
    vehicle: dict[str, Any] | None = None
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    inspection_results: list[dict[str, Any]] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)
    mileage: int | None = None
    appointments: list[dict[str, Any]] = field(default_factory=list)
    technician_notes: list[str] = field(default_factory=list)
    revenue_opportunities: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdvisorPlan:
    """Decide-only output — Decision Objects for Workflow execution."""

    decisions: list[Any] = field(default_factory=list)
    advisor_notes: str = ""
    queue_priority: str = "normal"
    suggestions: list[str] = field(default_factory=list)
    dashboard: dict[str, Any] = field(default_factory=dict)
