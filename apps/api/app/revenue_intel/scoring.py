"""Scoring: CLV, health bands, probability, ROI."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.revenue_intel.enums import HealthBand
from app.revenue_intel.models import CustomerSnapshot, HealthScore, VehicleSnapshot


def health_band(score: float) -> HealthBand:
    if score < 30:
        return HealthBand.CRITICAL
    if score < 50:
        return HealthBand.AT_RISK
    if score < 65:
        return HealthBand.FAIR
    if score < 80:
        return HealthBand.GOOD
    return HealthBand.EXCELLENT


def days_since(dt: datetime | None, *, now: datetime | None = None) -> int | None:
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((now - dt).total_seconds() / 86400))


def estimate_clv(customer: CustomerSnapshot, *, now: datetime | None = None) -> Decimal:
    """Simple CLV: avg ticket × expected remaining visits × retention."""
    now = now or datetime.now(timezone.utc)
    if customer.visit_count <= 0:
        return Decimal("0")
    avg_ticket = (customer.total_spend / customer.visit_count).quantize(Decimal("0.01"))
    tenure_days = days_since(customer.first_visit_at, now=now) or 365
    visits_per_year = customer.visit_count / max(tenure_days / 365.0, 0.25)
    inactive = days_since(customer.last_visit_at, now=now) or 0
    retention = 0.9
    if inactive > 365:
        retention = 0.2
    elif inactive > 180:
        retention = 0.45
    elif inactive > 90:
        retention = 0.7
    remaining_years = 3.0 * retention
    clv = avg_ticket * Decimal(str(visits_per_year)) * Decimal(str(remaining_years))
    return clv.quantize(Decimal("0.01"))


def score_customer(customer: CustomerSnapshot, *, now: datetime | None = None) -> HealthScore:
    now = now or datetime.now(timezone.utc)
    inactive = days_since(customer.last_visit_at, now=now)
    factors: dict[str, float] = {}
    notes: list[str] = []

    # Recency (40)
    if inactive is None:
        recency = 40.0
    elif inactive <= 60:
        recency = 40.0
    elif inactive <= 120:
        recency = 30.0
    elif inactive <= 180:
        recency = 20.0
        notes.append("No visit in 4–6 months")
    elif inactive <= 365:
        recency = 10.0
        notes.append("At risk of churn")
    else:
        recency = 0.0
        notes.append("Lost customer (>1 year)")
    factors["recency"] = recency

    # Frequency (25)
    freq = min(25.0, customer.visit_count * 4.0)
    factors["frequency"] = freq

    # Monetary / CLV (25)
    clv = float(estimate_clv(customer, now=now))
    monetary = min(25.0, clv / 200.0)
    factors["monetary"] = monetary

    # Engagement via communications (10)
    eng = min(10.0, len(customer.communications) * 2.0)
    factors["engagement"] = eng

    if customer.declined_estimates:
        notes.append(f"{len(customer.declined_estimates)} declined estimate(s)")

    score = sum(factors.values())
    return HealthScore(
        entity_id=customer.id,
        entity_type="customer",
        score=round(score, 1),
        band=health_band(score),
        factors=factors,
        notes=notes,
    )


def score_vehicle(vehicle: VehicleSnapshot, *, now: datetime | None = None) -> HealthScore:
    now = now or datetime.now(timezone.utc)
    current_year = now.year
    age = max(0, current_year - vehicle.year)
    factors: dict[str, float] = {}
    notes: list[str] = []

    # Age (30) — newer is healthier for retention value, older needs more service
    if age <= 3:
        age_score = 30.0
    elif age <= 7:
        age_score = 22.0
    elif age <= 12:
        age_score = 14.0
        notes.append("Aging vehicle — maintenance opportunities")
    else:
        age_score = 8.0
        notes.append("High-age vehicle")
    factors["age"] = age_score

    # Mileage vs age (30)
    expected_miles = max(age, 1) * 12000
    ratio = vehicle.mileage / expected_miles if expected_miles else 1.0
    if ratio < 0.8:
        mile_score = 30.0
    elif ratio < 1.2:
        mile_score = 22.0
    elif ratio < 1.6:
        mile_score = 14.0
        notes.append("Above-average mileage")
    else:
        mile_score = 6.0
        notes.append("High mileage — overdue services likely")
    factors["mileage"] = mile_score

    # Service recency (25)
    last_repair = max(
        (r.performed_at for r in vehicle.repairs if r.performed_at),
        default=None,
    )
    inactive = days_since(last_repair, now=now)
    if inactive is None:
        svc = 10.0
        notes.append("No repair history on file")
    elif inactive <= 90:
        svc = 25.0
    elif inactive <= 180:
        svc = 18.0
    elif inactive <= 365:
        svc = 10.0
    else:
        svc = 4.0
    factors["service_recency"] = svc

    # Open recommendations (15)
    open_recs = sum(1 for r in vehicle.repairs if r.recommendation and not r.declined)
    declined = sum(1 for r in vehicle.repairs if r.declined)
    rec_score = max(0.0, 15.0 - declined * 3.0 + min(open_recs, 3))
    factors["recommendations"] = min(15.0, rec_score)

    score = sum(factors.values())
    return HealthScore(
        entity_id=vehicle.id,
        entity_type="vehicle",
        score=round(min(100.0, score), 1),
        band=health_band(score),
        factors=factors,
        notes=notes,
    )


def compute_roi(*, expected_revenue: Decimal, probability: float, contact_cost: Decimal) -> float:
    invest = float(contact_cost) if contact_cost > 0 else 1.5
    expected = float(expected_revenue) * probability
    return round((expected - invest) / invest, 2)
