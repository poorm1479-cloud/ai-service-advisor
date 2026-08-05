"""In-memory parts / stock / supplier / reservation store with seed catalog."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from app.plugins.inventory.models import (
    PartCatalogItem,
    ReservationRecord,
    StockLevel,
    StockStatus,
    SupplierRecord,
)


def _seed_catalog() -> list[PartCatalogItem]:
    return [
        PartCatalogItem(
            sku="BRK-PAD-F",
            name="Front Brake Pads",
            brand="Akebono",
            category="brakes",
            oem_number="04465-0XXXX",
            unit_cost=Decimal("42.00"),
            list_price=Decimal("89.00"),
            compatible_services=["brake_inspection", "brake_service", "brakes_service"],
        ),
        PartCatalogItem(
            sku="BRK-ROT-F",
            name="Front Brake Rotor",
            brand="Raybestos",
            category="brakes",
            unit_cost=Decimal("55.00"),
            list_price=Decimal("110.00"),
            compatible_services=["brake_inspection", "brake_service", "brakes_service"],
        ),
        PartCatalogItem(
            sku="OIL-5W30",
            name="Synthetic Oil 5W-30 (5qt)",
            brand="Mobil 1",
            category="fluids",
            unit_cost=Decimal("28.00"),
            list_price=Decimal("49.00"),
            compatible_services=["oil_change", "fluids_service", "maintenance"],
        ),
        PartCatalogItem(
            sku="FLT-OIL",
            name="Oil Filter",
            brand="OEM",
            category="fluids",
            unit_cost=Decimal("8.00"),
            list_price=Decimal("18.00"),
            compatible_services=["oil_change", "fluids_service"],
        ),
        PartCatalogItem(
            sku="BAT-12V",
            name="12V AGM Battery",
            brand="Odyssey",
            category="electrical",
            unit_cost=Decimal("145.00"),
            list_price=Decimal("249.00"),
            compatible_services=["battery_test", "electrical_service"],
        ),
        PartCatalogItem(
            sku="BLT-SERP",
            name="Serpentine Belt",
            brand="Gates",
            category="engine",
            unit_cost=Decimal("22.00"),
            list_price=Decimal("45.00"),
            compatible_services=["engine_service", "diagnostics", "general_inspection"],
        ),
        PartCatalogItem(
            sku="TIR-225",
            name="All-Season Tire 225/65R17",
            brand="Michelin",
            category="tires",
            unit_cost=Decimal("120.00"),
            list_price=Decimal("189.00"),
            compatible_services=["tire_balance", "tires_service"],
        ),
        PartCatalogItem(
            sku="AC-COMP",
            name="A/C Compressor",
            brand="Denso",
            category="hvac",
            unit_cost=Decimal("280.00"),
            list_price=Decimal("420.00"),
            compatible_services=["ac_service", "hvac_service"],
        ),
    ]


def _seed_suppliers() -> list[SupplierRecord]:
    return [
        SupplierRecord(
            name="WorldPac",
            lead_time_days=1,
            reliability=0.95,
            part_skus=["BRK-PAD-F", "BRK-ROT-F", "OIL-5W30", "FLT-OIL", "BLT-SERP"],
        ),
        SupplierRecord(
            name="NAPA Auto Parts",
            lead_time_days=2,
            reliability=0.9,
            part_skus=["BAT-12V", "TIR-225", "AC-COMP", "BRK-PAD-F"],
        ),
        SupplierRecord(
            name="Dealer OEM Direct",
            lead_time_days=4,
            reliability=0.98,
            part_skus=["AC-COMP", "BAT-12V", "BRK-ROT-F"],
        ),
    ]


class InventoryStore:
    """Shop-scoped in-memory inventory (plugin-local, no DB migration)."""

    def __init__(self) -> None:
        self.parts: dict[UUID, PartCatalogItem] = {}
        self.parts_by_sku: dict[str, UUID] = {}
        self.stock: dict[tuple[UUID, UUID], StockLevel] = {}  # (shop_id, part_id)
        self.suppliers: dict[UUID, SupplierRecord] = {}
        self.reservations: dict[UUID, ReservationRecord] = {}
        self._seed()

    def _seed(self) -> None:
        for part in _seed_catalog():
            self.parts[part.id] = part
            self.parts_by_sku[part.sku.upper()] = part.id
        for supplier in _seed_suppliers():
            self.suppliers[supplier.id] = supplier

    def ensure_shop_stock(self, shop_id: UUID) -> None:
        """Lazy-init default stock levels per shop."""
        defaults = {
            "BRK-PAD-F": (6, 2),
            "BRK-ROT-F": (2, 1),
            "OIL-5W30": (12, 4),
            "FLT-OIL": (15, 4),
            "BAT-12V": (1, 1),
            "BLT-SERP": (3, 1),
            "TIR-225": (0, 2),
            "AC-COMP": (0, 1),
        }
        for sku, (qty, reorder) in defaults.items():
            part_id = self.parts_by_sku.get(sku.upper())
            if part_id is None:
                continue
            key = (shop_id, part_id)
            if key in self.stock:
                continue
            status = StockStatus.IN_STOCK
            if qty == 0:
                status = StockStatus.OUT
            elif qty <= reorder:
                status = StockStatus.LOW
            self.stock[key] = StockLevel(
                part_id=part_id,
                shop_id=shop_id,
                quantity_on_hand=qty,
                quantity_reserved=0,
                reorder_point=reorder,
                status=status,
            )

    def get_part_by_sku(self, sku: str) -> PartCatalogItem | None:
        pid = self.parts_by_sku.get(sku.upper())
        return self.parts.get(pid) if pid else None

    def get_part(self, part_id: UUID) -> PartCatalogItem | None:
        return self.parts.get(part_id)

    def search_parts(self, query: str, *, limit: int = 20) -> list[PartCatalogItem]:
        q = (query or "").strip().lower()
        if not q:
            return list(self.parts.values())[:limit]
        out: list[PartCatalogItem] = []
        for part in self.parts.values():
            hay = f"{part.sku} {part.name} {part.brand} {part.category} {part.oem_number or ''}".lower()
            if q in hay or any(q in s.lower() for s in part.compatible_services):
                out.append(part)
            if len(out) >= limit:
                break
        return out

    def parts_for_service(self, service_type: str) -> list[PartCatalogItem]:
        key = (service_type or "").lower()
        return [
            p
            for p in self.parts.values()
            if key in p.compatible_services
            or any(key in s or s in key for s in p.compatible_services)
            or key.split("_")[0] in p.category
        ]

    def get_stock(self, shop_id: UUID, part_id: UUID) -> StockLevel | None:
        self.ensure_shop_stock(shop_id)
        return self.stock.get((shop_id, part_id))

    def refresh_status(self, level: StockLevel) -> StockLevel:
        if level.available <= 0:
            level.status = StockStatus.OUT if level.quantity_on_hand <= 0 else StockStatus.RESERVED
        elif level.available <= level.reorder_point:
            level.status = StockStatus.LOW
        else:
            level.status = StockStatus.IN_STOCK
        return level

    def find_suppliers_for_sku(self, sku: str) -> list[SupplierRecord]:
        sku_u = sku.upper()
        matches = [s for s in self.suppliers.values() if sku_u in {x.upper() for x in s.part_skus}]
        return sorted(matches, key=lambda s: (s.lead_time_days, -s.reliability))

    def save_reservation(self, reservation: ReservationRecord) -> ReservationRecord:
        self.reservations[reservation.id] = reservation
        return reservation

    def get_reservation(self, reservation_id: UUID) -> ReservationRecord | None:
        return self.reservations.get(reservation_id)

    def clear(self) -> None:
        self.stock.clear()
        self.reservations.clear()
        # keep catalog/suppliers
