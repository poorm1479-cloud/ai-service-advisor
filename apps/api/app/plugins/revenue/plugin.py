"""Revenue Intelligence Plugin — wraps revenue_intel (no rewrite)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.plugins.framework.capability import Capability
from app.plugins.framework.context import PluginContext
from app.plugins.revenue.campaigns.service import CampaignsPluginService
from app.plugins.revenue.opportunity.service import OpportunityPluginService
from app.plugins.revenue.prediction.service import PredictionPluginService
from app.plugins.revenue.recommendations.service import RecommendationsPluginService
from app.plugins.revenue.retention.service import RetentionPluginService


class RevenuePlugin:
    """IPlugin + IRevenuePlugin — opportunity prioritization engine for Workflow."""

    def __init__(
        self,
        *,
        service: Any,
        engine: Any | None = None,
        store: Any | None = None,
        monitor: Any | None = None,
    ) -> None:
        self._service = service
        self._engine = engine
        self._store = store or getattr(service, "_store", None)
        self._monitor = monitor
        self._opportunity = OpportunityPluginService(
            service=service, engine=engine, store=self._store
        )
        self._retention = RetentionPluginService(service=service, store=self._store)
        self._prediction = PredictionPluginService(service=service, store=self._store)
        self._recommendations = RecommendationsPluginService(service=service)
        self._campaigns = CampaignsPluginService()
        self._initialized = False

    def plugin_id(self) -> str:
        return "revenue"

    def plugin_name(self) -> str:
        return "Revenue Intelligence Plugin"

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return (
            "Detect and prioritize revenue opportunities: retention, maintenance, "
            "upsell/cross-sell, declined estimates, CLV, and capacity optimization."
        )

    def supported_capabilities(self) -> list[str]:
        return [
            Capability.DETECT_REVENUE_OPPORTUNITY.value,
            Capability.PREDICT_MAINTENANCE.value,
            Capability.PREDICT_CUSTOMER_RETURN.value,
            Capability.FIND_DECLINED_ESTIMATES.value,
            Capability.GENERATE_UPSELL_RECOMMENDATIONS.value,
            Capability.GENERATE_CROSS_SELL_RECOMMENDATIONS.value,
            Capability.CALCULATE_VEHICLE_HEALTH.value,
            Capability.CALCULATE_CUSTOMER_HEALTH.value,
            Capability.CALCULATE_CUSTOMER_LIFETIME_VALUE.value,
            Capability.PREDICT_SHOP_CAPACITY.value,
            Capability.OPTIMIZE_TECHNICIAN_UTILIZATION.value,
            # Phase 20
            Capability.ANALYZE_CUSTOMER_VALUE.value,
            Capability.PREDICT_CUSTOMER_RISK.value,
            Capability.RECOMMEND_SERVICE.value,
            Capability.RECOMMEND_CONTACT_TIMING.value,
            Capability.CREATE_RETENTION_PLAN.value,
            Capability.ANALYZE_LOST_REVENUE.value,
            Capability.GENERATE_CAMPAIGN_SUGGESTION.value,
        ]

    def capabilities(self) -> list[str]:
        return self.supported_capabilities()

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
            "capabilities": len(self.supported_capabilities()),
            "monitor": self._monitor.snapshot() if self._monitor and hasattr(self._monitor, "snapshot") else {},
        }

    @property
    def service(self) -> Any:
        """Underlying RevenueIntelService for DI compatibility."""
        return self._service

    @property
    def opportunities(self) -> OpportunityPluginService:
        return self._opportunity

    @property
    def retention(self) -> RetentionPluginService:
        return self._retention

    @property
    def prediction(self) -> PredictionPluginService:
        return self._prediction

    @property
    def recommendations(self) -> RecommendationsPluginService:
        return self._recommendations

    @property
    def campaigns(self) -> CampaignsPluginService:
        return self._campaigns

    async def live_snapshot(self, shop_id: UUID, **kwargs: Any) -> dict[str, Any]:
        """Executive / analytics live source — no direct revenue_intel import needed."""
        run_analysis = bool(kwargs.get("run_analysis", False))
        from app.plugins.revenue.models import from_intel_opportunity

        if run_analysis:
            report = await self._service.run_nightly_analysis(shop_id)
            raw_opps = list(report.opportunities)
            dash = report.dashboard
        else:
            dash = await self._service.build_dashboard(shop_id)
            if getattr(dash, "open_opportunities", 0) == 0:
                report = await self._service.run_nightly_analysis(shop_id)
                dash = report.dashboard
                raw_opps = list(report.opportunities)
            else:
                raw_opps = await self._service.list_opportunities(shop_id, limit=50)
        views = [from_intel_opportunity(o) for o in raw_opps]
        board = self._campaigns.dashboard(opportunities=views, intel_dashboard=dash)
        util = await self._prediction.optimize_technician_utilization(shop_id)
        board["technician_efficiency"] = util
        board["monthly_revenue_forecast"] = board["intel"].get("forecast")
        return {
            "monitor": self._monitor.snapshot()
            if self._monitor and hasattr(self._monitor, "snapshot")
            else {},
            "dashboard": dash,
            # Preserve revenue_intel.Opportunity shape for executive widgets
            "opportunities": raw_opps[:20],
            "opportunity_views": views[:20],
            "board": board,
        }

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        if context is not None:
            for key, value in context.to_kwargs().items():
                if key.startswith("_"):
                    continue
                kwargs.setdefault(key, value)

        shop_id: UUID = kwargs["shop_id"]
        emit_events = bool(kwargs.get("emit_workflow_events", False))

        if capability == Capability.DETECT_REVENUE_OPPORTUNITY:
            run = kwargs.get("run_analysis", True)
            if run is None:
                run = True
            opps = await self._opportunity.detect(
                shop_id,
                run_analysis=bool(run),
                limit=int(kwargs.get("limit") or 200),
            )
            events = self._campaigns.workflow_events_for(shop_id, opps[:25])
            if emit_events:
                await self._emit_events(shop_id, events, kwargs.get("emit_fn"))
            return {
                "opportunities": opps,
                "count": len(opps),
                "workflow_events": events,
            }

        if capability == Capability.PREDICT_MAINTENANCE:
            return await self._prediction.predict_maintenance(
                shop_id, limit=int(kwargs.get("limit") or 100)
            )

        if capability == Capability.PREDICT_CUSTOMER_RETURN:
            return await self._retention.predict_customer_return(
                shop_id, limit=int(kwargs.get("limit") or 100)
            )

        if capability == Capability.FIND_DECLINED_ESTIMATES:
            return await self._opportunity.find_declined(
                shop_id, limit=int(kwargs.get("limit") or 100)
            )

        if capability == Capability.GENERATE_UPSELL_RECOMMENDATIONS:
            return await self._recommendations.generate_upsells(
                shop_id, limit=int(kwargs.get("limit") or 50)
            )

        if capability == Capability.GENERATE_CROSS_SELL_RECOMMENDATIONS:
            return await self._recommendations.generate_cross_sells(
                shop_id, limit=int(kwargs.get("limit") or 50)
            )

        if capability == Capability.CALCULATE_VEHICLE_HEALTH:
            return await self._prediction.calculate_vehicle_health(
                shop_id, kwargs.get("vehicle_id")
            )

        if capability == Capability.CALCULATE_CUSTOMER_HEALTH:
            return await self._retention.calculate_customer_health(
                shop_id, kwargs.get("customer_id")
            )

        if capability == Capability.CALCULATE_CUSTOMER_LIFETIME_VALUE:
            customer_id = kwargs.get("customer_id")
            if customer_id is None:
                raise ValueError("customer_id required")
            return await self._retention.calculate_customer_ltv(shop_id, customer_id)

        if capability == Capability.PREDICT_SHOP_CAPACITY:
            return await self._prediction.predict_shop_capacity(shop_id)

        if capability == Capability.OPTIMIZE_TECHNICIAN_UTILIZATION:
            return await self._prediction.optimize_technician_utilization(shop_id)

        # Phase 20 — analysis / suggestions only (never send marketing or mutate CRM)
        from app.revenue.factory import get_revenue_intelligence_runtime

        engine = get_revenue_intelligence_runtime().engine

        if capability == Capability.ANALYZE_CUSTOMER_VALUE:
            return await engine.analyze_customer_value(shop_id, kwargs.get("customer_id"))

        if capability == Capability.PREDICT_CUSTOMER_RISK:
            return await engine.predict_customer_risk(
                shop_id, kwargs.get("customer_id"), limit=int(kwargs.get("limit") or 50)
            )

        if capability == Capability.RECOMMEND_SERVICE:
            return await engine.recommend_service(shop_id, limit=int(kwargs.get("limit") or 50))

        if capability == Capability.RECOMMEND_CONTACT_TIMING:
            return await engine.recommend_contact_timing(
                shop_id,
                customer_id=kwargs.get("customer_id"),
                channel=str(kwargs.get("channel") or "sms"),
                preferences=kwargs.get("preferences"),
            )

        if capability == Capability.CREATE_RETENTION_PLAN:
            customer_id = kwargs.get("customer_id")
            if customer_id is None:
                raise ValueError("customer_id required for CreateRetentionPlan")
            result = await engine.create_retention_plan(shop_id, customer_id)
            decision = result.get("decision")
            return {
                **{k: v for k, v in result.items() if k != "decision"},
                "decision": decision,
                "decisions": [decision] if decision is not None else [],
            }

        if capability == Capability.ANALYZE_LOST_REVENUE:
            return await engine.analyze_lost_revenue(
                shop_id, limit=int(kwargs.get("limit") or 100)
            )

        if capability == Capability.GENERATE_CAMPAIGN_SUGGESTION:
            result = await engine.generate_campaign_suggestion(
                shop_id,
                customer_id=kwargs.get("customer_id"),
                campaign_type=str(kwargs.get("campaign_type") or "retention"),
                channel=str(kwargs.get("channel") or "sms"),
            )
            decision = result.get("decision")
            return {
                **{k: v for k, v in result.items() if k != "decision"},
                "decision": decision,
                "decisions": [decision] if decision is not None else [],
                "auto_send": False,
            }

        raise ValueError(f"Unknown revenue capability: {capability}")

    async def _emit_events(
        self, shop_id: UUID, events: list[dict[str, Any]], emit_fn: Any | None
    ) -> None:
        if not events:
            return
        if emit_fn is not None:
            for ev in events:
                await emit_fn(
                    shop_id=shop_id,
                    event_type=ev["event_type"],
                    payload=ev.get("payload") or {},
                    source="plugin.revenue",
                )
            return
        try:
            from app.workflows.enums import DomainEventType
            from app.workflows.factory import get_workflow_runtime

            rt = get_workflow_runtime()
            for ev in events:
                et = ev["event_type"]
                try:
                    et_enum = DomainEventType(et)
                except ValueError:
                    # Additive string events still publish via coordinator
                    et_enum = et
                await rt.coordinator.publish(
                    shop_id=shop_id,
                    event_type=et_enum,
                    payload=ev.get("payload") or {},
                    source="plugin.revenue",
                )
        except Exception:  # noqa: BLE001
            pass
