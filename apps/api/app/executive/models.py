"""Executive dashboard models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class DashboardCard:
    id: str
    label: str
    value: str
    delta: float | None = None  # percent change vs prior period
    unit: str | None = None
    tone: str = "neutral"  # positive | negative | neutral | warning
    detail: str | None = None


@dataclass(slots=True)
class ChartPoint:
    label: str
    value: float
    secondary: float | None = None


@dataclass(slots=True)
class ChartSeries:
    id: str
    title: str
    points: list[ChartPoint] = field(default_factory=list)
    unit: str | None = None


@dataclass(slots=True)
class WidgetItem:
    id: str
    title: str
    subtitle: str | None = None
    status: str | None = None
    priority: str = "normal"
    href: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Widget:
    id: str
    title: str
    items: list[WidgetItem] = field(default_factory=list)


@dataclass(slots=True)
class ExecutiveSnapshot:
    shop_id: UUID
    generated_at: datetime
    version: int
    cards: list[DashboardCard] = field(default_factory=list)
    charts: list[ChartSeries] = field(default_factory=list)
    widgets: list[Widget] = field(default_factory=list)
    live: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ShopLiveState:
    """Mutable realtime counters updated by domain events / polling refresh."""

    shop_id: UUID
    todays_revenue: Decimal = Decimal("0")
    expected_revenue: Decimal = Decimal("0")
    appointments_today: int = 0
    missed_calls: int = 0
    walk_ins_today: int = 0
    customers_total: int = 0
    ai_conversations: int = 0
    human_escalations: int = 0
    revenue_opportunities: int = 0
    marketing_roi: float = 0.0
    customer_satisfaction: float = 0.0
    mechanic_productivity: float = 0.0
    version: int = 1
    updated_at: datetime | None = None
