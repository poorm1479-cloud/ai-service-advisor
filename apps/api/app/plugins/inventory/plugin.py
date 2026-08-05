"""InventoryPlugin — Parts & Inventory Intelligence.

Connects repair recommendations with parts availability.
AI analysis returns Decision Objects only.
Reserve/Release are Workflow-facing mutations (never called by AI analyze path).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.inventory.models import InventoryContext, InventoryPlan
from app.plugins.inventory.ordering.service import OrderingService
from app.plugins.inventory.parts.service import PartsService
from app.plugins.inventory.prediction.service import PredictionService
from app.plugins.inventory.stock.service import StockService
from app.plugins.inventory.store import InventoryStore
from app.plugins.inventory.suppliers.service import SuppliersService


class InventoryPlugin:
    """IPlugin — Parts & Inventory Intelligence for AutoRepair OS."""

    def __init__(self, *, store: InventoryStore | None = None) -> None:
        self._store = store or InventoryStore()
        self._parts = PartsService(self._store)
        self._stock = StockService(self._store)
        self._suppliers = SuppliersService(self._store)
        self._ordering = OrderingService(self._store, self._suppliers)
        self._prediction = PredictionService(
            self._store,
            parts=self._parts,
            stock=self._stock,
            suppliers=self._suppliers,
            ordering=self._ordering,
        )
        self._initialized = False

    def plugin_id(self) -> str:
        return "inventory"

    def plugin_name(self) -> str:
        return "Parts & Inventory Intelligence"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Connects repair recommendations with real parts availability: "
            "search, stock, suppliers, readiness, and purchase recommendations. "
            "AI returns Decision Objects only — Workflow executes reservations/orders."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.FIND_PART.value,
            Capability.CHECK_INVENTORY.value,
            Capability.PREDICT_REQUIRED_PARTS.value,
            Capability.RESERVE_PART.value,
            Capability.RELEASE_PART.value,
            Capability.FIND_SUPPLIER.value,
            Capability.CREATE_PURCHASE_RECOMMENDATION.value,
            Capability.ESTIMATE_PART_COST.value,
            Capability.CHECK_REPAIR_READINESS.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "catalog_size": len(self._store.parts),
            "supplier_count": len(self._store.suppliers),
        }

    @property
    def store(self) -> InventoryStore:
        return self._store

    def build_context(self, **kwargs: Any) -> InventoryContext:
        shop_id = kwargs["shop_id"]
        payload = {k: v for k, v in kwargs.items() if k != "shop_id"}
        services = list(payload.get("service_types") or [])
        if payload.get("service_type"):
            services.append(str(payload["service_type"]))
        recs = list(payload.get("repair_recommendations") or payload.get("recommendations") or [])
        return InventoryContext(
            shop_id=shop_id,
            customer_id=payload.get("customer_id"),
            vehicle_id=payload.get("vehicle_id"),
            repair_id=payload.get("repair_id"),
            service_types=services,
            repair_recommendations=recs,
            channel=payload.get("channel") or "sms",
            metadata=dict(payload.get("metadata") or {}),
        )

    def analyze(self, ctx: InventoryContext) -> InventoryPlan:
        """Full inventory intelligence pass — Decision Objects only (no stock mutation)."""
        return self._prediction.analyze(ctx)

    def _plan_payload(self, plan: InventoryPlan) -> dict[str, Any]:
        return {
            "decisions": plan.decisions,
            "notes": plan.notes,
            "dashboard": plan.dashboard,
            "ready": plan.ready,
            "delay_days": plan.delay_days,
            "estimated_parts_cost": str(plan.estimated_parts_cost),
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        shop_id = kwargs.get("shop_id") or (context.shop_id if context else None)
        if shop_id is None:
            raise ValueError("shop_id required for Inventory Intelligence")
        if isinstance(shop_id, str):
            shop_id = UUID(shop_id)

        self._store.ensure_shop_stock(shop_id)
        payload = {k: v for k, v in kwargs.items() if k != "shop_id"}
        cap = capability if isinstance(capability, str) else str(capability)

        if cap in {Capability.FIND_PART.value, "FindPart"}:
            parts = self._parts.find(
                query=payload.get("query") or payload.get("q"),
                sku=payload.get("sku"),
                service_type=payload.get("service_type"),
                limit=int(payload.get("limit") or 20),
            )
            return {"parts": [self._parts.to_dict(p) for p in parts], "count": len(parts)}

        if cap in {Capability.CHECK_INVENTORY.value, "CheckInventory"}:
            part_id = payload.get("part_id")
            if isinstance(part_id, str):
                part_id = UUID(part_id)
            return self._stock.check(
                shop_id,
                sku=payload.get("sku"),
                part_id=part_id,
                quantity=int(payload.get("quantity") or 1),
            )

        if cap in {Capability.FIND_SUPPLIER.value, "FindSupplier"}:
            supplier_id = payload.get("supplier_id")
            if isinstance(supplier_id, str):
                supplier_id = UUID(supplier_id)
            suppliers = self._suppliers.find(
                sku=payload.get("sku"),
                supplier_id=supplier_id,
                name=payload.get("name"),
            )
            return {
                "suppliers": [self._suppliers.to_dict(s) for s in suppliers],
                "count": len(suppliers),
            }

        if cap in {Capability.RESERVE_PART.value, "ReservePart"}:
            repair_id = payload.get("repair_id")
            customer_id = payload.get("customer_id")
            if isinstance(repair_id, str):
                repair_id = UUID(repair_id)
            if isinstance(customer_id, str):
                customer_id = UUID(customer_id)
            return self._stock.reserve(
                shop_id,
                sku=str(payload.get("sku") or ""),
                quantity=int(payload.get("quantity") or 1),
                repair_id=repair_id,
                customer_id=customer_id,
            )

        if cap in {Capability.RELEASE_PART.value, "ReleasePart"}:
            reservation_id = payload.get("reservation_id")
            if isinstance(reservation_id, str):
                reservation_id = UUID(reservation_id)
            return self._stock.release(
                shop_id,
                reservation_id=reservation_id,
                sku=payload.get("sku"),
                quantity=payload.get("quantity"),
            )

        # --- AI decide-only capabilities below (no inventory mutation) ---
        ctx = self.build_context(shop_id=shop_id, **payload)

        if cap in {Capability.PREDICT_REQUIRED_PARTS.value, "PredictRequiredParts"}:
            lines = self._prediction.predict_required_parts(ctx)
            ctx.required_parts = lines
            return {
                "parts": [
                    {
                        "sku": line.sku,
                        "name": line.name,
                        "quantity": line.quantity,
                        "available": line.available,
                        "status": line.status.value,
                        "unit_cost": str(line.unit_cost),
                        "service_type": line.service_type,
                        "lead_time_days": line.lead_time_days,
                    }
                    for line in lines
                ],
                "count": len(lines),
                "decisions": [],  # full decisions via CheckRepairReadiness / analyze
            }

        if cap in {
            Capability.CREATE_PURCHASE_RECOMMENDATION.value,
            "CreatePurchaseRecommendation",
        }:
            ctx.required_parts = self._prediction.predict_required_parts(ctx)
            decisions = self._ordering.recommend(ctx)
            return {"decisions": decisions, "count": len(decisions)}

        if cap in {Capability.ESTIMATE_PART_COST.value, "EstimatePartCost"}:
            plan = self.analyze(ctx)
            cost_decisions = [
                d for d in plan.decisions if d.__class__.__name__ == "PartCostDecision"
            ]
            return {
                "decisions": cost_decisions,
                "estimated_parts_cost": str(plan.estimated_parts_cost),
                "count": len(cost_decisions),
            }

        if cap in {Capability.CHECK_REPAIR_READINESS.value, "CheckRepairReadiness"}:
            plan = self.analyze(ctx)
            return self._plan_payload(plan)

        raise LookupError(f"Unsupported inventory capability: {cap}")
