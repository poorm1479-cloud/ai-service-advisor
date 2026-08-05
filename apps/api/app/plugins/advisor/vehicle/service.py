"""Vehicle analysis — decide only from mileage / history context."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.decisions.types import RepairRecommendationDecision
from app.plugins.advisor.models import AdvisorContext

_KEYWORDS = {
    "brake": ("brakes", "Brake inspection / service", Decimal("349.00"), "high"),
    "oil": ("oil_change", "Oil change", Decimal("79.99"), "normal"),
    "tire": ("tires", "Tire evaluation", Decimal("199.00"), "normal"),
    "battery": ("battery", "Battery test / replacement", Decimal("189.00"), "high"),
    "noise": ("diagnostic", "Diagnostic inspection", Decimal("129.00"), "high"),
    "ac": ("ac_service", "A/C performance check", Decimal("159.00"), "normal"),
}


class AdvisorVehicleService:
    def analyze(self, ctx: AdvisorContext) -> list[Any]:
        decisions: list[Any] = []
        text = (ctx.inbound_text or "").lower()
        mileage = ctx.mileage or (ctx.vehicle or {}).get("mileage")
        label = _vehicle_label(ctx)

        for key, (service, title, cost, urgency) in _KEYWORDS.items():
            if key in text:
                decisions.append(
                    RepairRecommendationDecision(
                        customer_id=ctx.customer_id,
                        vehicle_id=ctx.vehicle_id,
                        service_type=service,
                        title=title,
                        description=f"Based on customer description for {label}",
                        estimated_cost=cost,
                        urgency=urgency,  # type: ignore[arg-type]
                        plain_language=(
                            f"We recommend {title.lower()} for your {label}. "
                            f"Estimated starting around ${cost}."
                        ),
                        advisor_notes=f"Triggered by keyword '{key}' in inbound message",
                        confidence=0.72,
                        rationale=f"Vehicle condition signal: {key}",
                    )
                )
                break

        if mileage and int(mileage) >= 60000 and not decisions:
            decisions.append(
                RepairRecommendationDecision(
                    customer_id=ctx.customer_id,
                    vehicle_id=ctx.vehicle_id,
                    service_type="inspection",
                    title="Mileage-based multi-point inspection",
                    description=f"Vehicle at ~{mileage} miles",
                    estimated_cost=Decimal("99.00"),
                    urgency="normal",
                    plain_language=(
                        f"Your {label} is around {mileage} miles — a multi-point inspection "
                        "helps catch wear items before they become costly repairs."
                    ),
                    advisor_notes="Mileage threshold recommendation",
                    confidence=0.65,
                    rationale="Mileage-based preventive maintenance",
                )
            )
        return decisions


def _vehicle_label(ctx: AdvisorContext) -> str:
    v = ctx.vehicle or {}
    parts = [str(v.get("year") or ""), str(v.get("make") or ""), str(v.get("model") or "")]
    label = " ".join(p for p in parts if p).strip()
    return label or "vehicle"
