"""Revenue intel store + demo customer seed data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from app.revenue_intel.enums import OpportunityHorizon, OpportunityKind, OpportunityStatus
from app.revenue_intel.models import (
    AnalysisJob,
    CommunicationSnapshot,
    CustomerSnapshot,
    HealthScore,
    Opportunity,
    RepairSnapshot,
    VehicleSnapshot,
)


class RevenueIntelStorePort(Protocol):
    async def list_customers(self, shop_id: UUID) -> list[CustomerSnapshot]: ...

    async def upsert_customer(self, customer: CustomerSnapshot) -> CustomerSnapshot: ...

    async def save_opportunities(self, items: list[Opportunity]) -> list[Opportunity]: ...

    async def list_opportunities(
        self,
        shop_id: UUID,
        *,
        horizon: OpportunityHorizon | None = None,
        kind: OpportunityKind | None = None,
        status: OpportunityStatus | None = None,
        limit: int = 200,
    ) -> list[Opportunity]: ...

    async def update_opportunity(self, opp: Opportunity) -> Opportunity: ...

    async def clear_open_opportunities(self, shop_id: UUID) -> None: ...

    async def save_scores(self, scores: list[HealthScore]) -> None: ...

    async def list_scores(
        self, shop_id: UUID, *, entity_type: str | None = None
    ) -> list[HealthScore]: ...

    async def save_job(self, job: AnalysisJob) -> AnalysisJob: ...

    async def get_job(self, shop_id: UUID, job_id: UUID) -> AnalysisJob | None: ...

    async def list_jobs(self, shop_id: UUID, *, limit: int = 20) -> list[AnalysisJob]: ...

    def ensure_shop(self, shop_id: UUID) -> None: ...


class InMemoryRevenueIntelStore:
    def __init__(self) -> None:
        self.customers: dict[UUID, list[CustomerSnapshot]] = {}
        self.opportunities: dict[UUID, list[Opportunity]] = {}
        self.scores: dict[UUID, list[HealthScore]] = {}
        self.jobs: dict[UUID, AnalysisJob] = {}
        self._seeded: set[UUID] = set()

    def ensure_shop(self, shop_id: UUID) -> None:
        """Initialize empty shop buckets — never auto-seed demo customers."""
        if shop_id in self._seeded:
            return
        self.customers.setdefault(shop_id, [])
        self.opportunities.setdefault(shop_id, [])
        self.scores.setdefault(shop_id, [])
        self._seeded.add(shop_id)

    def seed_demo_customers(self, shop_id: UUID) -> None:
        """Explicit demo seed for tests / optional demos only."""
        self.customers[shop_id] = _demo_customers(shop_id)
        self.opportunities.setdefault(shop_id, [])
        self.scores.setdefault(shop_id, [])
        self._seeded.add(shop_id)

    async def list_customers(self, shop_id: UUID) -> list[CustomerSnapshot]:
        self.ensure_shop(shop_id)
        return list(self.customers.get(shop_id, []))

    async def upsert_customer(self, customer: CustomerSnapshot) -> CustomerSnapshot:
        self.ensure_shop(customer.shop_id)
        items = self.customers.setdefault(customer.shop_id, [])
        for i, c in enumerate(items):
            if c.id == customer.id:
                items[i] = customer
                return customer
        items.append(customer)
        return customer

    async def save_opportunities(self, items: list[Opportunity]) -> list[Opportunity]:
        for opp in items:
            bucket = self.opportunities.setdefault(opp.shop_id, [])
            bucket.append(opp)
        return items

    async def list_opportunities(
        self,
        shop_id: UUID,
        *,
        horizon: OpportunityHorizon | None = None,
        kind: OpportunityKind | None = None,
        status: OpportunityStatus | None = None,
        limit: int = 200,
    ) -> list[Opportunity]:
        self.ensure_shop(shop_id)
        items = list(self.opportunities.get(shop_id, []))
        if horizon:
            items = [o for o in items if o.horizon == horizon]
        if kind:
            items = [o for o in items if o.kind == kind]
        if status:
            items = [o for o in items if o.status == status]
        items.sort(key=lambda o: (o.expected_revenue * Decimal(str(o.probability))), reverse=True)
        return items[:limit]

    async def update_opportunity(self, opp: Opportunity) -> Opportunity:
        bucket = self.opportunities.get(opp.shop_id, [])
        for i, existing in enumerate(bucket):
            if existing.id == opp.id:
                bucket[i] = opp
                return opp
        bucket.append(opp)
        self.opportunities[opp.shop_id] = bucket
        return opp

    async def clear_open_opportunities(self, shop_id: UUID) -> None:
        bucket = self.opportunities.get(shop_id, [])
        self.opportunities[shop_id] = [o for o in bucket if o.status != OpportunityStatus.OPEN]

    async def save_scores(self, scores: list[HealthScore]) -> None:
        by_shop: dict[UUID, list[HealthScore]] = {}
        # scores don't carry shop_id — store under last ensure; caller passes via service
        for s in scores:
            # attach later in service with shop key
            pass
        # Service will call save_shop_scores
        self._pending_scores = scores  # type: ignore[attr-defined]

    async def save_shop_scores(self, shop_id: UUID, scores: list[HealthScore]) -> None:
        self.scores[shop_id] = scores

    async def list_scores(
        self, shop_id: UUID, *, entity_type: str | None = None
    ) -> list[HealthScore]:
        self.ensure_shop(shop_id)
        items = list(self.scores.get(shop_id, []))
        if entity_type:
            items = [s for s in items if s.entity_type == entity_type]
        return items

    async def save_job(self, job: AnalysisJob) -> AnalysisJob:
        self.jobs[job.id] = job
        return job

    async def get_job(self, shop_id: UUID, job_id: UUID) -> AnalysisJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.shop_id != shop_id:
            return None
        return job

    async def list_jobs(self, shop_id: UUID, *, limit: int = 20) -> list[AnalysisJob]:
        items = [j for j in self.jobs.values() if j.shop_id == shop_id]
        items.sort(key=lambda j: j.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit]


def _demo_customers(shop_id: UUID) -> list[CustomerSnapshot]:
    now = datetime.now(timezone.utc)
    c1 = uuid4()
    c2 = uuid4()
    c3 = uuid4()
    c4 = uuid4()
    v1, v2, v3, v4 = uuid4(), uuid4(), uuid4(), uuid4()

    return [
        CustomerSnapshot(
            id=c1,
            shop_id=shop_id,
            name="Alex Rivera",
            phone="+15550100",
            email="alex@example.com",
            last_visit_at=now - timedelta(days=400),
            first_visit_at=now - timedelta(days=900),
            total_spend=Decimal("1840.00"),
            visit_count=6,
            vehicles=[
                VehicleSnapshot(
                    id=v1,
                    vin="1HGCM82633A004352",
                    year=2016,
                    make="Honda",
                    model="Accord",
                    mileage=98000,
                    repairs=[
                        RepairSnapshot(
                            "oil_change",
                            cost=Decimal("79.99"),
                            mileage=82000,
                            performed_at=now - timedelta(days=420),
                        ),
                        RepairSnapshot(
                            "brakes",
                            cost=Decimal("380"),
                            mileage=70000,
                            performed_at=now - timedelta(days=800),
                            recommendation="Replace pads within 6 months",
                        ),
                    ],
                )
            ],
            communications=[
                CommunicationSnapshot("sms", "outbound", "Reminder", now - timedelta(days=410)),
            ],
            declined_estimates=[{"service": "brakes", "amount": "420.00"}],
        ),
        CustomerSnapshot(
            id=c2,
            shop_id=shop_id,
            name="Jordan Lee",
            phone="+15550101",
            email="jordan@example.com",
            last_visit_at=now - timedelta(days=120),
            first_visit_at=now - timedelta(days=600),
            total_spend=Decimal("960.00"),
            visit_count=4,
            vehicles=[
                VehicleSnapshot(
                    id=v2,
                    vin="2T1BURHE0JC123456",
                    year=2019,
                    make="Toyota",
                    model="Corolla",
                    mileage=54000,
                    repairs=[
                        RepairSnapshot(
                            "oil_change",
                            cost=Decimal("79.99"),
                            mileage=48000,
                            performed_at=now - timedelta(days=200),
                        ),
                    ],
                )
            ],
            communications=[
                CommunicationSnapshot("email", "inbound", "Price question", now - timedelta(days=30)),
            ],
        ),
        CustomerSnapshot(
            id=c3,
            shop_id=shop_id,
            name="Sam Chen",
            phone="+15550102",
            last_visit_at=now - timedelta(days=20),
            first_visit_at=now - timedelta(days=200),
            total_spend=Decimal("540.00"),
            visit_count=3,
            vehicles=[
                VehicleSnapshot(
                    id=v3,
                    vin="3FA6P0H75ER123456",
                    year=2014,
                    make="Ford",
                    model="Fusion",
                    mileage=112000,
                    repairs=[
                        RepairSnapshot(
                            "battery",
                            cost=Decimal("160"),
                            mileage=90000,
                            performed_at=now - timedelta(days=900),
                        ),
                        RepairSnapshot(
                            "tires",
                            cost=Decimal("600"),
                            mileage=85000,
                            performed_at=now - timedelta(days=1000),
                        ),
                    ],
                )
            ],
        ),
        CustomerSnapshot(
            id=c4,
            shop_id=shop_id,
            name="Casey Morgan",
            email="casey@example.com",
            last_visit_at=now - timedelta(days=250),
            first_visit_at=now - timedelta(days=800),
            total_spend=Decimal("2100.00"),
            visit_count=8,
            vehicles=[
                VehicleSnapshot(
                    id=v4,
                    vin="5YJSA1E14HF123456",
                    year=2017,
                    make="Chevy",
                    model="Malibu",
                    mileage=76000,
                    repairs=[
                        RepairSnapshot(
                            "alignment",
                            cost=Decimal("120"),
                            mileage=60000,
                            performed_at=now - timedelta(days=500),
                        ),
                        RepairSnapshot(
                            "fluids",
                            cost=Decimal("140"),
                            mileage=55000,
                            performed_at=now - timedelta(days=600),
                        ),
                    ],
                )
            ],
            declined_estimates=[{"service": "tires", "amount": "680.00"}],
        ),
    ]
