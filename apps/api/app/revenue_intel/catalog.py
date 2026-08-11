"""Service catalog: intervals, prices, seasonality weights."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.revenue_intel.enums import OpportunityKind


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    kind: OpportunityKind
    service_key: str
    label: str
    interval_miles: int
    interval_days: int
    base_price: Decimal
    contact_cost: Decimal = Decimal("1.50")  # SMS/email outreach cost for ROI


SERVICE_CATALOG: dict[str, ServiceSpec] = {
    "oil_change": ServiceSpec(
        OpportunityKind.OIL_CHANGE, "oil_change", "Oil change", 5000, 180, Decimal("79.99")
    ),
    "brakes": ServiceSpec(
        OpportunityKind.BRAKES, "brakes", "Brake replacement", 30000, 730, Decimal("420.00")
    ),
    "battery": ServiceSpec(
        OpportunityKind.BATTERY, "battery", "Battery replacement", 50000, 1095, Decimal("189.99")
    ),
    "tires": ServiceSpec(
        OpportunityKind.TIRES, "tires", "Tire replacement", 40000, 1095, Decimal("650.00")
    ),
    "alignment": ServiceSpec(
        OpportunityKind.ALIGNMENT, "alignment", "Wheel alignment", 15000, 365, Decimal("129.99")
    ),
    "fluids": ServiceSpec(
        OpportunityKind.FLUIDS, "fluids", "Fluid service", 30000, 730, Decimal("149.99")
    ),
}

# Alias keys often seen in repair history / shop catalog names
SERVICE_ALIASES: dict[str, str] = {
    "oil": "oil_change",
    "oil_change": "oil_change",
    "synthetic_oil_change": "oil_change",
    "brake": "brakes",
    "brakes": "brakes",
    "brake_service": "brakes",
    "brake_repair": "brakes",
    "brake_inspection": "brakes",
    "brake_replacement": "brakes",
    "front_brake_pad_replacement": "brakes",
    "battery": "battery",
    "tire": "tires",
    "tires": "tires",
    "tire_rotation": "tires",
    "tire_replacement": "tires",
    "tire_mount": "tires",
    "alignment": "alignment",
    "wheel_alignment": "alignment",
    "fluid": "fluids",
    "fluids": "fluids",
    "coolant": "fluids",
    "transmission_service": "fluids",
}

# Ordered token → catalog key for shop names like "Brake Repair", "Tire Rotation"
_SERVICE_TOKENS: tuple[tuple[str, str], ...] = (
    ("oil", "oil_change"),
    ("brake", "brakes"),
    ("tire", "tires"),
    ("battery", "battery"),
    ("align", "alignment"),
    ("fluid", "fluids"),
    ("coolant", "fluids"),
)

# Month (1-12) → relative demand boost for each service key
SEASONALITY: dict[str, dict[int, float]] = {
    "battery": {1: 0.25, 2: 0.2, 12: 0.3},  # winter
    "tires": {10: 0.2, 11: 0.25, 3: 0.15, 4: 0.15},
    "ac": {5: 0.2, 6: 0.3, 7: 0.3, 8: 0.25},
    "oil_change": {3: 0.1, 4: 0.1, 9: 0.1, 10: 0.1},
    "brakes": {11: 0.1, 12: 0.1, 1: 0.1},
    "alignment": {3: 0.15, 4: 0.15},
    "fluids": {5: 0.1, 6: 0.1},
}


def resolve_service_key(raw: str) -> str | None:
    """Map free-text / shop catalog service names onto SERVICE_CATALOG keys."""
    text = (raw or "").strip().lower()
    if not text:
        return None
    key = text.replace(" ", "_").replace("-", "_")
    if key in SERVICE_CATALOG:
        return key
    aliased = SERVICE_ALIASES.get(key) or SERVICE_ALIASES.get(text)
    if aliased:
        return aliased
    for token, catalog_key in _SERVICE_TOKENS:
        if token in key or token in text:
            return catalog_key
    return None


def seasonality_boost(service_key: str, month: int) -> float:
    return SEASONALITY.get(service_key, {}).get(month, 0.0)
