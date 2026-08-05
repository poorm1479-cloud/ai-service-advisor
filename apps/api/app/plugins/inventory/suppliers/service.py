"""Supplier lookup."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.inventory.models import SupplierRecord
from app.plugins.inventory.store import InventoryStore


class SuppliersService:
    def __init__(self, store: InventoryStore) -> None:
        self._store = store

    def find(
        self,
        *,
        sku: str | None = None,
        supplier_id: UUID | None = None,
        name: str | None = None,
    ) -> list[SupplierRecord]:
        if supplier_id:
            s = self._store.suppliers.get(supplier_id)
            return [s] if s else []
        if sku:
            return self._store.find_suppliers_for_sku(sku)
        if name:
            q = name.lower()
            return [s for s in self._store.suppliers.values() if q in s.name.lower()]
        return list(self._store.suppliers.values())

    def to_dict(self, supplier: SupplierRecord) -> dict[str, Any]:
        return {
            "id": str(supplier.id),
            "name": supplier.name,
            "lead_time_days": supplier.lead_time_days,
            "reliability": supplier.reliability,
            "phone": supplier.phone,
            "email": supplier.email,
            "part_skus": list(supplier.part_skus),
        }

    def best_for_sku(self, sku: str) -> SupplierRecord | None:
        matches = self.find(sku=sku)
        return matches[0] if matches else None
