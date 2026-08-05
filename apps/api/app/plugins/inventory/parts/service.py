"""Part catalog search."""

from __future__ import annotations

from typing import Any

from app.plugins.inventory.models import PartCatalogItem
from app.plugins.inventory.store import InventoryStore


class PartsService:
    def __init__(self, store: InventoryStore) -> None:
        self._store = store

    def find(
        self,
        *,
        query: str | None = None,
        sku: str | None = None,
        service_type: str | None = None,
        limit: int = 20,
    ) -> list[PartCatalogItem]:
        if sku:
            part = self._store.get_part_by_sku(sku)
            return [part] if part else []
        if service_type:
            return self._store.parts_for_service(service_type)[:limit]
        return self._store.search_parts(query or "", limit=limit)

    def to_dict(self, part: PartCatalogItem) -> dict[str, Any]:
        return {
            "id": str(part.id),
            "sku": part.sku,
            "name": part.name,
            "brand": part.brand,
            "category": part.category,
            "oem_number": part.oem_number,
            "unit_cost": str(part.unit_cost),
            "list_price": str(part.list_price),
            "compatible_services": list(part.compatible_services),
        }
