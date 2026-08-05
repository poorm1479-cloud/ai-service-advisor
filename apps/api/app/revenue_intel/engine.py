"""Core analysis engine — nightly customer scan → opportunities."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.revenue_intel.catalog import (
    SERVICE_CATALOG,
    resolve_service_key,
    seasonality_boost,
)
from app.revenue_intel.enums import (
    OpportunityHorizon,
    OpportunityKind,
    OpportunityStatus,
)
from app.revenue_intel.messaging import recommend_channel, recommend_message
from app.revenue_intel.models import (
    CustomerSnapshot,
    ForecastPoint,
    HealthScore,
    MonthlyForecast,
    Opportunity,
    RepairSnapshot,
    RoiPoint,
    VehicleSnapshot,
)
from app.revenue_intel.scoring import (
    compute_roi,
    days_since,
    estimate_clv,
    score_customer,
    score_vehicle,
)


def _vehicle_label(v: VehicleSnapshot) -> str:
    return f"{v.year} {v.make} {v.model}".strip()


def _last_service(vehicle: VehicleSnapshot, service_key: str) -> RepairSnapshot | None:
    matches = []
    for r in vehicle.repairs:
        key = resolve_service_key(r.service_type)
        if key == service_key:
            matches.append(r)
    if not matches:
        return None
    return max(matches, key=lambda r: r.performed_at or datetime.min.replace(tzinfo=timezone.utc))


def _is_overdue(
    vehicle: VehicleSnapshot,
    service_key: str,
    *,
    now: datetime,
) -> tuple[bool, str]:
    spec = SERVICE_CATALOG[service_key]
    last = _last_service(vehicle, service_key)
    if last is None:
        # Never serviced — overdue if mileage or age suggests it
        if vehicle.mileage >= spec.interval_miles:
            return True, f"No {spec.label} on record; mileage {vehicle.mileage:,} exceeds interval"
        age_days = max(0, (now.year - vehicle.year) * 365)
        if age_days >= spec.interval_days:
            return True, f"No {spec.label} on record; vehicle age exceeds interval"
        return False, ""
    miles_since = vehicle.mileage - (last.mileage or 0)
    days = days_since(last.performed_at, now=now) or 0
    if miles_since >= spec.interval_miles:
        return True, f"{spec.label} overdue by mileage ({miles_since:,} since last)"
    if days >= spec.interval_days:
        return True, f"{spec.label} overdue by time ({days} days since last)"
    return False, ""


def _horizon_for(contact_date: date, *, today: date) -> OpportunityHorizon:
    delta = (contact_date - today).days
    if delta <= 1:
        return OpportunityHorizon.DAILY
    if delta <= 7:
        return OpportunityHorizon.WEEKLY
    return OpportunityHorizon.MONTHLY


def _probability(
    *,
    base: float,
    customer_health: float,
    seasonality: float,
    declined: bool = False,
    lost: bool = False,
) -> float:
    p = base
    p += (customer_health - 50) / 200.0
    p += seasonality
    if declined:
        p += 0.08
    if lost:
        p -= 0.15
    return round(min(0.95, max(0.05, p)), 3)


class RevenueAnalysisEngine:
    """Analyze all customers and emit scored opportunities."""

    def analyze_customer(
        self,
        customer: CustomerSnapshot,
        *,
        now: datetime | None = None,
        job_id: UUID | None = None,
    ) -> tuple[list[Opportunity], HealthScore, list[HealthScore]]:
        now = now or datetime.now(timezone.utc)
        today = now.date()
        c_score = score_customer(customer, now=now)
        v_scores: list[HealthScore] = []
        opps: list[Opportunity] = []
        clv = estimate_clv(customer, now=now)
        inactive = days_since(customer.last_visit_at, now=now)

        # Lost / return likelihood
        if inactive is not None and inactive > 365:
            opps.append(
                self._make_opp(
                    customer,
                    vehicle=None,
                    kind=OpportunityKind.LOST_CUSTOMER,
                    title="Win back lost customer",
                    reason=f"No visit in {inactive} days; CLV ${clv}",
                    revenue=max(clv * Decimal("0.15"), Decimal("120")),
                    base_prob=0.28,
                    customer_health=c_score.score,
                    vehicle_health=None,
                    contact_date=today,
                    service=None,
                    now=now,
                    job_id=job_id,
                    lost=True,
                )
            )
        elif inactive is not None and 90 <= inactive <= 365:
            opps.append(
                self._make_opp(
                    customer,
                    vehicle=None,
                    kind=OpportunityKind.LIKELY_RETURN,
                    title="Customer likely to return",
                    reason=f"Visit cadence suggests return window ({inactive} days since last)",
                    revenue=max(customer.total_spend / max(customer.visit_count, 1), Decimal("99")),
                    base_prob=0.55,
                    customer_health=c_score.score,
                    vehicle_health=None,
                    contact_date=today + timedelta(days=1),
                    service=None,
                    now=now,
                    job_id=job_id,
                )
            )

        # Declined estimates
        for est in customer.declined_estimates:
            service = str(est.get("service") or est.get("service_type") or "repair")
            amount = Decimal(str(est.get("amount") or est.get("total") or "150"))
            vehicle = customer.vehicles[0] if customer.vehicles else None
            v_health = score_vehicle(vehicle, now=now).score if vehicle else None
            opps.append(
                self._make_opp(
                    customer,
                    vehicle=vehicle,
                    kind=OpportunityKind.DECLINED_ESTIMATE,
                    title=f"Revisit declined {service}",
                    reason="Previously declined estimate — high acceptance if reframed",
                    revenue=amount,
                    base_prob=0.42,
                    customer_health=c_score.score,
                    vehicle_health=v_health,
                    contact_date=today + timedelta(days=2),
                    service=service,
                    now=now,
                    job_id=job_id,
                    declined=True,
                )
            )
            opps.append(
                self._make_opp(
                    customer,
                    vehicle=vehicle,
                    kind=OpportunityKind.LIKELY_ACCEPT,
                    title=f"Likely to accept {service}",
                    reason="Acceptance model based on prior estimate + engagement",
                    revenue=amount,
                    base_prob=0.48,
                    customer_health=c_score.score,
                    vehicle_health=v_health,
                    contact_date=today + timedelta(days=3),
                    service=service,
                    now=now,
                    job_id=job_id,
                    declined=True,
                )
            )

        for vehicle in customer.vehicles:
            v_score = score_vehicle(vehicle, now=now)
            v_scores.append(v_score)
            label = _vehicle_label(vehicle)

            any_overdue = False
            for key, spec in SERVICE_CATALOG.items():
                overdue, reason = _is_overdue(vehicle, key, now=now)
                if not overdue:
                    continue
                any_overdue = True
                boost = seasonality_boost(key, now.month)
                # sooner contact for safety-critical
                delay = 0 if key in {"brakes", "battery"} else 1
                opps.append(
                    self._make_opp(
                        customer,
                        vehicle=vehicle,
                        kind=spec.kind,
                        title=f"{spec.label} — {label}",
                        reason=reason,
                        revenue=spec.base_price * (Decimal("1") + Decimal(str(boost))),
                        base_prob=0.5 + boost / 2,
                        customer_health=c_score.score,
                        vehicle_health=v_score.score,
                        contact_date=today + timedelta(days=delay),
                        service=spec.label,
                        now=now,
                        job_id=job_id,
                        seasonality=boost,
                        contact_cost=spec.contact_cost,
                    )
                )

            if any_overdue:
                opps.append(
                    self._make_opp(
                        customer,
                        vehicle=vehicle,
                        kind=OpportunityKind.MAINTENANCE_OVERDUE,
                        title=f"Maintenance overdue — {label}",
                        reason="One or more scheduled services exceed mileage/time intervals",
                        revenue=Decimal("199.00"),
                        base_prob=0.52,
                        customer_health=c_score.score,
                        vehicle_health=v_score.score,
                        contact_date=today,
                        service="maintenance package",
                        now=now,
                        job_id=job_id,
                    )
                )

        return opps, c_score, v_scores

    def _make_opp(
        self,
        customer: CustomerSnapshot,
        *,
        vehicle: VehicleSnapshot | None,
        kind: OpportunityKind,
        title: str,
        reason: str,
        revenue: Decimal,
        base_prob: float,
        customer_health: float,
        vehicle_health: float | None,
        contact_date: date,
        service: str | None,
        now: datetime,
        job_id: UUID | None,
        seasonality: float = 0.0,
        contact_cost: Decimal = Decimal("1.50"),
        declined: bool = False,
        lost: bool = False,
    ) -> Opportunity:
        today = now.date()
        prob = _probability(
            base=base_prob,
            customer_health=customer_health,
            seasonality=seasonality,
            declined=declined,
            lost=lost,
        )
        revenue = revenue.quantize(Decimal("0.01"))
        roi = compute_roi(expected_revenue=revenue, probability=prob, contact_cost=contact_cost)
        channel = recommend_channel(customer, kind)
        label = _vehicle_label(vehicle) if vehicle else None
        return Opportunity(
            id=uuid4(),
            shop_id=customer.shop_id,
            customer_id=customer.id,
            vehicle_id=vehicle.id if vehicle else None,
            kind=kind,
            horizon=_horizon_for(contact_date, today=today),
            title=title,
            reason=reason,
            expected_revenue=revenue,
            probability=prob,
            expected_roi=roi,
            recommended_contact_date=contact_date,
            recommended_channel=channel,
            recommended_message=recommend_message(
                kind=kind, customer=customer, vehicle_label=label, service=service
            ),
            customer_name=customer.name,
            vehicle_label=label,
            customer_health=customer_health,
            vehicle_health=vehicle_health,
            status=OpportunityStatus.OPEN,
            seasonality_boost=seasonality,
            metadata={"clv": str(estimate_clv(customer, now=now))},
            created_at=now,
            analysis_job_id=job_id,
        )

    def build_forecast(
        self,
        shop_id: UUID,
        opportunities: list[Opportunity],
        *,
        as_of: date | None = None,
    ) -> MonthlyForecast:
        as_of = as_of or date.today()
        months: list[ForecastPoint] = []
        total = Decimal("0")
        for i in range(3):
            year = as_of.year + (as_of.month + i - 1) // 12
            month = (as_of.month + i - 1) % 12 + 1
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            bucket = [
                o
                for o in opportunities
                if o.status == OpportunityStatus.OPEN and start <= o.recommended_contact_date <= end
            ]
            if i == 0:
                # also include daily/weekly already due
                bucket = [
                    o
                    for o in opportunities
                    if o.status == OpportunityStatus.OPEN
                    and o.recommended_contact_date <= end
                    and o.recommended_contact_date >= as_of - timedelta(days=7)
                ]
            expected = sum(
                (o.expected_revenue * Decimal(str(o.probability)) for o in bucket),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            avg_p = sum(o.probability for o in bucket) / len(bucket) if bucket else 0.0
            months.append(
                ForecastPoint(
                    period_start=start,
                    period_end=end,
                    expected_revenue=expected,
                    opportunity_count=len(bucket),
                    win_probability_avg=round(avg_p, 3),
                    label=start.strftime("%b %Y"),
                )
            )
            total += expected
        return MonthlyForecast(shop_id=shop_id, as_of=as_of, months=months, total_expected=total)

    def build_roi_series(self, opportunities: list[Opportunity]) -> list[RoiPoint]:
        by_kind: dict[OpportunityKind, list[Opportunity]] = {}
        for o in opportunities:
            if o.status != OpportunityStatus.OPEN:
                continue
            by_kind.setdefault(o.kind, []).append(o)
        points: list[RoiPoint] = []
        for kind, items in sorted(by_kind.items(), key=lambda kv: kv[0].value):
            invested = Decimal("1.50") * len(items)
            expected = sum(
                (i.expected_revenue * Decimal(str(i.probability)) for i in items),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            roi = compute_roi(
                expected_revenue=expected,
                probability=1.0,
                contact_cost=invested if invested > 0 else Decimal("1.50"),
            )
            points.append(
                RoiPoint(
                    label=kind.value,
                    invested=invested.quantize(Decimal("0.01")),
                    expected_return=expected,
                    roi=roi,
                    opportunity_count=len(items),
                )
            )
        return points
