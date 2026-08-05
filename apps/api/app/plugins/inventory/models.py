"""Parts & Inventory Intelligence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW = "low"
    OUT = "out_of_stock"
    ON_ORDER = "on_order"
    RESERVED = "reserved"


class LeadTimeRisk(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(slots=True)
class PartCatalogItem:
    id: UUID = field(default_factory=uuid4)
    sku: str = ""
    name: str = ""
    brand: str = ""
    category: str = "general"
    oem_number: str | None = None
    unit_cost: Decimal = Decimal("0.00")
    list_price: Decimal = Decimal("0.00")
    compatible_services: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StockLevel:
    part_id: UUID
    shop_id: UUID
    quantity_on_hand: int = 0
    quantity_reserved: int = 0
    reorder_point: int = 2
    status: StockStatus = StockStatus.IN_STOCK

    @property
    def available(self) -> int:
        return max(0, self.quantity_on_hand - self.quantity_reserved)


@dataclass(slots=True)
class SupplierRecord:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    lead_time_days: int = 2
    reliability: float = 0.9
    phone: str | None = None
    email: str | None = None
    part_skus: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReservationRecord:
    id: UUID = field(default_factory=uuid4)
    shop_id: UUID | None = None
    part_id: UUID | None = None
    sku: str = ""
    quantity: int = 1
    repair_id: UUID | None = None
    customer_id: UUID | None = None
    status: Literal["active", "released", "consumed"] = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class RequiredPartLine:
    sku: str
    name: str
    quantity: int = 1
    service_type: str = "general"
    unit_cost: Decimal = Decimal("0.00")
    available: int = 0
    status: StockStatus = StockStatus.OUT
    supplier_id: UUID | None = None
    lead_time_days: int = 0


@dataclass(slots=True)
class InventoryContext:
    """Context for inventory intelligence (AI decide-only analysis)."""

    shop_id: UUID
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    service_types: list[str] = field(default_factory=list)
    repair_recommendations: list[dict[str, Any]] = field(default_factory=list)
    required_parts: list[RequiredPartLine] = field(default_factory=list)
    channel: str = "sms"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InventoryPlan:
    """Bundle of Decision Objects from inventory analysis."""

    decisions: list[Any] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ready: bool = False
    estimated_parts_cost: Decimal = Decimal("0.00")
    delay_days: int = 0
    dashboard: dict[str, Any] = field(default_factory=dict)
