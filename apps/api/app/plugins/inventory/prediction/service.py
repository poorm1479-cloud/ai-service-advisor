"""Predict parts, readiness, cost, and availability — Decision Objects only."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.decisions.types import (
    InventoryRiskDecision,
    PartCostDecision,
    PartsAvailabilityDecision,
    RepairReadinessDecision,
)
from app.plugins.inventory.models import (
    InventoryContext,
    InventoryPlan,
    RequiredPartLine,
    StockStatus,
)
from app.plugins.inventory.ordering.service import OrderingService
from app.plugins.inventory.parts.service import PartsService
from app.plugins.inventory.stock.service import StockService
from app.plugins.inventory.store import InventoryStore
from app.plugins.inventory.suppliers.service import SuppliersService


_SERVICE_QTY: dict[str, int] = {
    "brake": 1,
    "oil": 1,
    "tire": 4,
    "battery": 1,
    "ac": 1,
}


class PredictionService:
    """AI inventory intelligence — never mutates stock or places orders."""

    def __init__(
        self,
        store: InventoryStore,
        *,
        parts: PartsService | None = None,
        stock: StockService | None = None,
        suppliers: SuppliersService | None = None,
        ordering: OrderingService | None = None,
    ) -> None:
        self._store = store
        self._parts = parts or PartsService(store)
        self._stock = stock or StockService(store)
        self._suppliers = suppliers or SuppliersService(store)
        self._ordering = ordering or OrderingService(store, self._suppliers)

    def predict_required_parts(self, ctx: InventoryContext) -> list[RequiredPartLine]:
        services = list(ctx.service_types)
        for rec in ctx.repair_recommendations:
            st = str(rec.get("service_type") or rec.get("service") or "")
            if st and st not in services:
                services.append(st)

        lines: list[RequiredPartLine] = []
        seen: set[str] = set()
        for service in services:
            qty_hint = 1
            for key, q in _SERVICE_QTY.items():
                if key in service.lower():
                    qty_hint = q
                    break
            for part in self._parts.find(service_type=service, limit=5):
                if part.sku in seen:
                    continue
                seen.add(part.sku)
                check = self._stock.check(ctx.shop_id, sku=part.sku, quantity=qty_hint)
                supplier = self._suppliers.best_for_sku(part.sku)
                status = StockStatus(check.get("status") or StockStatus.OUT.value)
                lines.append(
                    RequiredPartLine(
                        sku=part.sku,
                        name=part.name,
                        quantity=qty_hint,
                        service_type=service,
                        unit_cost=part.unit_cost,
                        available=int(check.get("available") or 0),
                        status=status,
                        supplier_id=supplier.id if supplier else None,
                        lead_time_days=supplier.lead_time_days if supplier else 3,
                    )
                )
        # Explicit SKUs from metadata / recommendations
        for rec in ctx.repair_recommendations:
            for sku in rec.get("skus") or rec.get("parts") or []:
                sku_s = str(sku)
                if sku_s in seen:
                    continue
                part = self._store.get_part_by_sku(sku_s)
                if not part:
                    continue
                seen.add(part.sku)
                check = self._stock.check(ctx.shop_id, sku=part.sku, quantity=1)
                supplier = self._suppliers.best_for_sku(part.sku)
                lines.append(
                    RequiredPartLine(
                        sku=part.sku,
                        name=part.name,
                        quantity=1,
                        service_type=str(rec.get("service_type") or "general"),
                        unit_cost=part.unit_cost,
                        available=int(check.get("available") or 0),
                        status=StockStatus(check.get("status") or StockStatus.OUT.value),
                        supplier_id=supplier.id if supplier else None,
                        lead_time_days=supplier.lead_time_days if supplier else 3,
                    )
                )
        return lines

    def analyze(self, ctx: InventoryContext) -> InventoryPlan:
        if not ctx.required_parts:
            ctx.required_parts = self.predict_required_parts(ctx)

        decisions: list[Any] = []
        notes: list[str] = []
        lines = ctx.required_parts
        notes.append(f"Predicted {len(lines)} required part line(s)")

        missing: list[dict[str, Any]] = []
        available_lines: list[dict[str, Any]] = []
        delay = 0
        total_cost = Decimal("0.00")

        for line in lines:
            line_cost = line.unit_cost * Decimal(line.quantity)
            total_cost += line_cost
            snap = {
                "sku": line.sku,
                "name": line.name,
                "quantity": line.quantity,
                "available": line.available,
                "status": line.status.value,
                "unit_cost": str(line.unit_cost),
                "line_cost": str(line_cost),
                "lead_time_days": line.lead_time_days,
            }
            sufficient = line.available >= line.quantity
            if sufficient:
                available_lines.append(snap)
            else:
                missing.append(snap)
                delay = max(delay, line.lead_time_days)
            decisions.append(
                PartsAvailabilityDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    repair_id=ctx.repair_id,
                    sku=line.sku,
                    part_name=line.name,
                    quantity_needed=line.quantity,
                    quantity_available=line.available,
                    status=line.status.value,
                    sufficient=sufficient,
                    reserve_recommended=sufficient,
                    lead_time_days=0 if sufficient else line.lead_time_days,
                    confidence=0.88,
                    rationale=f"Availability check for {line.sku}",
                )
            )
            decisions.append(
                PartCostDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    repair_id=ctx.repair_id,
                    sku=line.sku,
                    part_name=line.name,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    line_cost=line_cost,
                    list_price_hint=None,
                    confidence=0.85,
                    rationale=f"Part cost estimate for {line.sku}",
                )
            )

        purchases = self._ordering.recommend(ctx)
        decisions.extend(purchases)

        if missing or any(l.status == StockStatus.LOW for l in lines):
            risk = "high" if delay >= 3 or any(l.status == StockStatus.OUT for l in lines) else "medium"
            decisions.append(
                InventoryRiskDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    repair_id=ctx.repair_id,
                    risk_level=risk,  # type: ignore[arg-type]
                    delay_days=delay,
                    missing_skus=[m["sku"] for m in missing],
                    message=(
                        f"{len(missing)} part(s) unavailable; estimated delay {delay} day(s)."
                        if missing
                        else "Low stock risk detected for recommended repairs."
                    ),
                    confidence=0.84,
                    rationale="Inventory risk from parts availability gaps",
                )
            )

        ready = len(missing) == 0 and len(lines) > 0
        blocking = [m["name"] for m in missing]
        decisions.append(
            RepairReadinessDecision(
                customer_id=ctx.customer_id,
                vehicle_id=ctx.vehicle_id,
                repair_id=ctx.repair_id,
                ready=ready,
                delay_days=delay,
                blocking_parts=blocking,
                parts_cost_total=total_cost,
                schedule_adjustment="delay" if delay > 0 else ("proceed" if ready else "noop"),
                customer_message=(
                    "Parts are ready — we can proceed with the repair."
                    if ready
                    else (
                        f"We're waiting on parts ({', '.join(blocking[:3])})"
                        + (f"; about {delay} day(s)." if delay else ".")
                    )
                ),
                confidence=0.87,
                rationale="Repair readiness from inventory analysis",
            )
        )

        return InventoryPlan(
            decisions=decisions,
            notes=notes,
            ready=ready,
            estimated_parts_cost=total_cost,
            delay_days=delay,
            dashboard={
                "required_count": len(lines),
                "available_count": len(available_lines),
                "missing_count": len(missing),
                "purchase_recommendations": len(purchases),
                "ready": ready,
                "delay_days": delay,
                "estimated_parts_cost": str(total_cost),
                "missing": missing,
                "available": available_lines,
            },
        )
