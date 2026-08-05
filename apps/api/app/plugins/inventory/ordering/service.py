"""Purchase recommendations — Decision Objects only (never executes purchases)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.decisions.types import PurchaseRecommendationDecision
from app.plugins.inventory.models import InventoryContext, RequiredPartLine, StockStatus
from app.plugins.inventory.store import InventoryStore
from app.plugins.inventory.suppliers.service import SuppliersService


class OrderingService:
    def __init__(self, store: InventoryStore, suppliers: SuppliersService | None = None) -> None:
        self._store = store
        self._suppliers = suppliers or SuppliersService(store)

    def recommend(self, ctx: InventoryContext) -> list[PurchaseRecommendationDecision]:
        decisions: list[PurchaseRecommendationDecision] = []
        for line in ctx.required_parts:
            if line.status in {StockStatus.IN_STOCK, StockStatus.RESERVED} and line.available >= line.quantity:
                continue
            shortfall = max(0, line.quantity - line.available)
            if shortfall <= 0 and line.status == StockStatus.LOW:
                shortfall = max(1, line.quantity)
            supplier = self._suppliers.best_for_sku(line.sku)
            lead = supplier.lead_time_days if supplier else max(line.lead_time_days, 3)
            est_cost = line.unit_cost * Decimal(shortfall or line.quantity)
            decisions.append(
                PurchaseRecommendationDecision(
                    shop_hint=str(ctx.shop_id),
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    repair_id=ctx.repair_id,
                    sku=line.sku,
                    part_name=line.name,
                    quantity=shortfall or line.quantity,
                    supplier_id=supplier.id if supplier else None,
                    supplier_name=supplier.name if supplier else None,
                    lead_time_days=lead,
                    estimated_cost=est_cost,
                    urgency="high" if lead >= 3 or line.status == StockStatus.OUT else "normal",
                    reason=f"Insufficient stock for {line.name} ({line.status.value})",
                    confidence=0.86,
                    rationale="Purchase recommendation — AI decide-only; Workflow may order",
                )
            )
        return decisions

    def lines_needing_purchase(self, lines: list[RequiredPartLine]) -> list[RequiredPartLine]:
        return [
            line
            for line in lines
            if line.available < line.quantity or line.status in {StockStatus.OUT, StockStatus.LOW}
        ]
