"""Revenue Intelligence service — nightly job + dashboard queries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.revenue_intel.engine import RevenueAnalysisEngine
from app.revenue_intel.enums import (
    JobStatus,
    OpportunityHorizon,
    OpportunityKind,
    OpportunityStatus,
)
from app.revenue_intel.models import (
    AnalysisJob,
    DashboardSummary,
    HealthScore,
    MonthlyForecast,
    NightlyReport,
    Opportunity,
)
from app.revenue_intel.store import InMemoryRevenueIntelStore, RevenueIntelStorePort


class RevenueIntelService:
    def __init__(
        self,
        *,
        store: RevenueIntelStorePort,
        engine: RevenueAnalysisEngine | None = None,
    ) -> None:
        self._store = store
        self._engine = engine or RevenueAnalysisEngine()

    async def run_nightly_analysis(
        self, shop_id: UUID, *, now: datetime | None = None
    ) -> NightlyReport:
        now = now or datetime.now(timezone.utc)
        if hasattr(self._store, "ensure_shop"):
            self._store.ensure_shop(shop_id)

        job = AnalysisJob(
            id=uuid4(),
            shop_id=shop_id,
            status=JobStatus.RUNNING,
            started_at=now,
        )
        await self._store.save_job(job)

        try:
            customers = await self._store.list_customers(shop_id)
            await self._store.clear_open_opportunities(shop_id)

            all_opps: list[Opportunity] = []
            customer_scores: list[HealthScore] = []
            vehicle_scores: list[HealthScore] = []

            for customer in customers:
                opps, c_score, v_scores = self._engine.analyze_customer(
                    customer, now=now, job_id=job.id
                )
                all_opps.extend(opps)
                customer_scores.append(c_score)
                vehicle_scores.extend(v_scores)

            await self._store.save_opportunities(all_opps)
            if isinstance(self._store, InMemoryRevenueIntelStore):
                await self._store.save_shop_scores(shop_id, customer_scores + vehicle_scores)
            else:
                await self._store.save_scores(customer_scores + vehicle_scores)

            forecast = self._engine.build_forecast(shop_id, all_opps, as_of=now.date())
            dashboard = await self.build_dashboard(shop_id, now=now, forecast=forecast)

            job.status = JobStatus.COMPLETED
            job.customers_analyzed = len(customers)
            job.opportunities_created = len(all_opps)
            job.finished_at = datetime.now(timezone.utc)
            job.summary = {
                "expected_daily": str(dashboard.expected_revenue_daily),
                "expected_weekly": str(dashboard.expected_revenue_weekly),
                "expected_monthly": str(dashboard.expected_revenue_monthly),
                "avg_customer_health": dashboard.avg_customer_health,
                "avg_vehicle_health": dashboard.avg_vehicle_health,
            }
            await self._store.save_job(job)

            return NightlyReport(
                job=job,
                opportunities=all_opps,
                customer_scores=customer_scores,
                vehicle_scores=vehicle_scores,
                forecast=forecast,
                dashboard=dashboard,
            )
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            await self._store.save_job(job)
            raise

    async def build_dashboard(
        self,
        shop_id: UUID,
        *,
        now: datetime | None = None,
        forecast: MonthlyForecast | None = None,
    ) -> DashboardSummary:
        now = now or datetime.now(timezone.utc)
        if hasattr(self._store, "ensure_shop"):
            self._store.ensure_shop(shop_id)

        open_opps = await self._store.list_opportunities(
            shop_id, status=OpportunityStatus.OPEN, limit=1000
        )
        if forecast is None:
            forecast = self._engine.build_forecast(shop_id, open_opps, as_of=now.date())

        def weighted(items: list[Opportunity]) -> Decimal:
            return sum(
                (o.expected_revenue * Decimal(str(o.probability)) for o in items),
                Decimal("0"),
            ).quantize(Decimal("0.01"))

        daily = [o for o in open_opps if o.horizon == OpportunityHorizon.DAILY]
        weekly = [
            o
            for o in open_opps
            if o.horizon in {OpportunityHorizon.DAILY, OpportunityHorizon.WEEKLY}
        ]

        scores = await self._store.list_scores(shop_id)
        c_scores = [s.score for s in scores if s.entity_type == "customer"]
        v_scores = [s.score for s in scores if s.entity_type == "vehicle"]

        kind_counts: dict[str, int] = {}
        for o in open_opps:
            kind_counts[o.kind.value] = kind_counts.get(o.kind.value, 0) + 1
        top_kinds = [
            {"kind": k, "count": c}
            for k, c in sorted(kind_counts.items(), key=lambda x: x[1], reverse=True)[:8]
        ]

        return DashboardSummary(
            shop_id=shop_id,
            as_of=now,
            expected_revenue_daily=weighted(daily),
            expected_revenue_weekly=weighted(weekly),
            expected_revenue_monthly=forecast.total_expected,
            open_opportunities=len(open_opps),
            lost_customers=sum(1 for o in open_opps if o.kind == OpportunityKind.LOST_CUSTOMER),
            maintenance_overdue=sum(
                1 for o in open_opps if o.kind == OpportunityKind.MAINTENANCE_OVERDUE
            ),
            avg_customer_health=round(sum(c_scores) / len(c_scores), 1) if c_scores else 0.0,
            avg_vehicle_health=round(sum(v_scores) / len(v_scores), 1) if v_scores else 0.0,
            avg_probability=(
                round(sum(o.probability for o in open_opps) / len(open_opps), 3) if open_opps else 0.0
            ),
            avg_roi=(
                round(sum(o.expected_roi for o in open_opps) / len(open_opps), 2) if open_opps else 0.0
            ),
            top_kinds=top_kinds,
            roi_series=self._engine.build_roi_series(open_opps),
            forecast=forecast,
        )

    async def list_opportunities(
        self,
        shop_id: UUID,
        *,
        horizon: OpportunityHorizon | None = None,
        kind: OpportunityKind | None = None,
        status: OpportunityStatus | None = OpportunityStatus.OPEN,
        limit: int = 200,
    ) -> list[Opportunity]:
        if hasattr(self._store, "ensure_shop"):
            self._store.ensure_shop(shop_id)
        return await self._store.list_opportunities(
            shop_id, horizon=horizon, kind=kind, status=status, limit=limit
        )

    async def update_opportunity_status(
        self, shop_id: UUID, opportunity_id: UUID, status: OpportunityStatus
    ) -> Opportunity:
        items = await self._store.list_opportunities(shop_id, status=None, limit=5000)
        opp = next((o for o in items if o.id == opportunity_id), None)
        if opp is None:
            raise LookupError("Opportunity not found")
        opp.status = status
        return await self._store.update_opportunity(opp)

    async def get_forecast(self, shop_id: UUID) -> MonthlyForecast:
        opps = await self.list_opportunities(shop_id)
        return self._engine.build_forecast(shop_id, opps)

    async def list_scores(
        self, shop_id: UUID, *, entity_type: str | None = None
    ) -> list[HealthScore]:
        if hasattr(self._store, "ensure_shop"):
            self._store.ensure_shop(shop_id)
        return await self._store.list_scores(shop_id, entity_type=entity_type)

    async def list_jobs(self, shop_id: UUID, *, limit: int = 20) -> list[AnalysisJob]:
        return await self._store.list_jobs(shop_id, limit=limit)

    async def get_job(self, shop_id: UUID, job_id: UUID) -> AnalysisJob:
        job = await self._store.get_job(shop_id, job_id)
        if job is None:
            raise LookupError("Analysis job not found")
        return job
