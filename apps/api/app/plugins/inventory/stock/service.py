"""Stock checking and reservations (Workflow-facing mutations)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.plugins.inventory.models import ReservationRecord, StockLevel, StockStatus
from app.plugins.inventory.store import InventoryStore


class StockService:
    def __init__(self, store: InventoryStore) -> None:
        self._store = store

    def check(
        self,
        shop_id: UUID,
        *,
        sku: str | None = None,
        part_id: UUID | None = None,
        quantity: int = 1,
    ) -> dict[str, Any]:
        self._store.ensure_shop_stock(shop_id)
        part = None
        if sku:
            part = self._store.get_part_by_sku(sku)
        elif part_id:
            part = self._store.get_part(part_id)
        if part is None:
            return {
                "found": False,
                "sku": sku,
                "available": 0,
                "status": StockStatus.OUT.value,
                "sufficient": False,
            }
        level = self._store.get_stock(shop_id, part.id)
        if level is None:
            return {
                "found": True,
                "part_id": str(part.id),
                "sku": part.sku,
                "name": part.name,
                "available": 0,
                "status": StockStatus.OUT.value,
                "sufficient": False,
                "quantity_requested": quantity,
            }
        self._store.refresh_status(level)
        return {
            "found": True,
            "part_id": str(part.id),
            "sku": part.sku,
            "name": part.name,
            "available": level.available,
            "on_hand": level.quantity_on_hand,
            "reserved": level.quantity_reserved,
            "reorder_point": level.reorder_point,
            "status": level.status.value,
            "sufficient": level.available >= quantity,
            "quantity_requested": quantity,
            "unit_cost": str(part.unit_cost),
            "list_price": str(part.list_price),
        }

    def reserve(
        self,
        shop_id: UUID,
        *,
        sku: str,
        quantity: int = 1,
        repair_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Workflow-only mutation — AI must not call this during decide-only analysis."""
        part = self._store.get_part_by_sku(sku)
        if part is None:
            return {"ok": False, "error": f"Unknown SKU {sku}"}
        level = self._store.get_stock(shop_id, part.id)
        if level is None or level.available < quantity:
            return {
                "ok": False,
                "error": "Insufficient stock",
                "available": level.available if level else 0,
            }
        level.quantity_reserved += quantity
        self._store.refresh_status(level)
        reservation = ReservationRecord(
            id=uuid4(),
            shop_id=shop_id,
            part_id=part.id,
            sku=part.sku,
            quantity=quantity,
            repair_id=repair_id,
            customer_id=customer_id,
            status="active",
        )
        self._store.save_reservation(reservation)
        return {
            "ok": True,
            "reservation_id": str(reservation.id),
            "sku": part.sku,
            "quantity": quantity,
            "available_after": level.available,
            "status": level.status.value,
        }

    def release(
        self,
        shop_id: UUID,
        *,
        reservation_id: UUID | None = None,
        sku: str | None = None,
        quantity: int | None = None,
    ) -> dict[str, Any]:
        """Workflow-only mutation — release reserved quantity."""
        reservation: ReservationRecord | None = None
        if reservation_id:
            reservation = self._store.get_reservation(reservation_id)
        if reservation is None and sku:
            for r in self._store.reservations.values():
                if (
                    r.shop_id == shop_id
                    and r.sku.upper() == sku.upper()
                    and r.status == "active"
                ):
                    reservation = r
                    break
        if reservation is None or reservation.status != "active":
            return {"ok": False, "error": "Active reservation not found"}
        if reservation.shop_id != shop_id:
            return {"ok": False, "error": "Reservation shop mismatch"}

        qty = quantity or reservation.quantity
        part_id = reservation.part_id
        if part_id:
            level = self._store.get_stock(shop_id, part_id)
            if level:
                level.quantity_reserved = max(0, level.quantity_reserved - qty)
                self._store.refresh_status(level)
        reservation.status = "released"
        return {
            "ok": True,
            "reservation_id": str(reservation.id),
            "sku": reservation.sku,
            "quantity_released": qty,
        }

    def level_snapshot(self, level: StockLevel) -> dict[str, Any]:
        self._store.refresh_status(level)
        return {
            "part_id": str(level.part_id),
            "available": level.available,
            "on_hand": level.quantity_on_hand,
            "reserved": level.quantity_reserved,
            "status": level.status.value,
        }
