"""Core KPI computation engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.analytics.benchmarks import apply_benchmark_fields, compare_benchmarks
from app.analytics.enums import KpiId, TrendDirection
from app.analytics.forecast import ForecastEngine
from app.analytics.models import (
    AnalyticsSnapshot,
    ChartSeries,
    KpiMetric,
    SeriesPoint,
    ShopMetricFact,
)
from app.analytics.monitoring import AnalyticsMonitor
from app.analytics.seed import seed_shop_facts
from app.analytics.store import AnalyticsStorePort


def _pct_delta(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / abs(previous)) * 100.0, 2)


def _trend(delta: float) -> TrendDirection:
    if delta > 1.5:
        return TrendDirection.UP
    if delta < -1.5:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


class AnalyticsEngine:
    def __init__(
        self,
        store: AnalyticsStorePort,
        *,
        forecast: ForecastEngine | None = None,
        monitor: AnalyticsMonitor | None = None,
    ) -> None:
        self._store = store
        self._forecast = forecast or ForecastEngine(monitor)
        self._monitor = monitor or AnalyticsMonitor()

    def ensure_facts(self, shop_id: UUID, *, days: int = 90) -> list[ShopMetricFact]:
        """Return existing facts only — do not invent demo history for empty shops."""
        _ = days  # API compatibility; use seed_demo_facts for explicit demos
        return self._store.list_facts(shop_id)

    def seed_demo_facts(self, shop_id: UUID, *, days: int = 90) -> list[ShopMetricFact]:
        """Explicit demo seed for tests / optional demos only."""
        seeded = seed_shop_facts(self._store, shop_id, days=days)
        self._monitor.record_facts(len(seeded))
        return self._store.list_facts(shop_id)

    def build_snapshot(
        self,
        shop_id: UUID,
        *,
        period_days: int = 30,
        forecast_horizon: int = 30,
        now: datetime | None = None,
    ) -> AnalyticsSnapshot:
        now = now or datetime.now(timezone.utc)
        end = now.date()
        start = end - timedelta(days=period_days - 1)
        facts = self.ensure_facts(shop_id)
        period = [f for f in facts if start <= f.day <= end]
        prev_start = start - timedelta(days=period_days)
        prev_end = start - timedelta(days=1)
        previous = [f for f in facts if prev_start <= f.day <= prev_end]
        if not period:
            period = facts[-period_days:]
        if not previous:
            previous = facts[-(period_days * 2) : -period_days] or period

        sources = self._pull_live_sources(shop_id)
        kpis = self._compute_kpis(period, previous, sources=sources)
        apply_benchmark_fields(kpis)
        charts = self._charts(period, facts)
        forecasts = [
            self._forecast.forecast_revenue(facts, horizon_days=forecast_horizon),
            self._forecast.forecast_kpi_series(
                KpiId.APPOINTMENT_CONVERSION,
                [
                    (f.appointments_booked / f.appointments_offered)
                    if f.appointments_offered
                    else 0.0
                    for f in facts
                ],
                facts[-1].day if facts else end,
                horizon_days=min(14, forecast_horizon),
            ),
        ]
        benchmarks = compare_benchmarks(kpis)
        snap = AnalyticsSnapshot(
            shop_id=shop_id,
            generated_at=now,
            period_start=start,
            period_end=end,
            kpis=kpis,
            charts=charts,
            forecasts=forecasts,
            benchmarks=benchmarks,
            sources=sources,
            version=(self._store.get_snapshot(shop_id).version + 1)
            if self._store.get_snapshot(shop_id)
            else 1,
        )
        saved = self._store.save_snapshot(snap)
        self._monitor.record_snapshot()
        return saved

    def _compute_kpis(
        self,
        period: list[ShopMetricFact],
        previous: list[ShopMetricFact],
        *,
        sources: dict[str, Any],
    ) -> list[KpiMetric]:
        def sum_rev(rows: list[ShopMetricFact]) -> float:
            return float(sum((f.revenue for f in rows), Decimal("0")))

        def sum_ros(rows: list[ShopMetricFact]) -> int:
            return sum(f.repair_orders for f in rows)

        rev = sum_rev(period)
        rev_prev = sum_rev(previous)
        ros = sum_ros(period) or 1
        ros_prev = sum_ros(previous) or 1
        aro = rev / ros
        aro_prev = rev_prev / ros_prev

        active = sum(f.customers_active for f in period) or 1
        returning = sum(f.customers_returning for f in period)
        retention = returning / active
        active_p = sum(f.customers_active for f in previous) or 1
        retention_prev = sum(f.customers_returning for f in previous) / active_p

        offered = sum(f.appointments_offered for f in period) or 1
        booked = sum(f.appointments_booked for f in period)
        conv = booked / offered
        offered_p = sum(f.appointments_offered for f in previous) or 1
        conv_prev = sum(f.appointments_booked for f in previous) / offered_p

        m_spend = float(sum((f.marketing_spend for f in period), Decimal("0"))) or 1.0
        m_rev = float(sum((f.marketing_revenue for f in period), Decimal("0")))
        roi = m_rev / m_spend
        m_spend_p = float(sum((f.marketing_spend for f in previous), Decimal("0"))) or 1.0
        roi_prev = float(sum((f.marketing_revenue for f in previous), Decimal("0"))) / m_spend_p

        mech = sum(f.mechanic_hours for f in period) or 1.0
        billed = sum(f.billed_hours for f in period)
        prod = billed / mech
        mech_p = sum(f.mechanic_hours for f in previous) or 1.0
        prod_prev = sum(f.billed_hours for f in previous) / mech_p

        ai_c = sum(f.ai_conversations for f in period) or 1
        ai_ok = sum(f.ai_resolved for f in period)
        ai_rate = ai_ok / ai_c
        ai_c_p = sum(f.ai_conversations for f in previous) or 1
        ai_prev = sum(f.ai_resolved for f in previous) / ai_c_p

        clv = float(period[-1].clv_cohort_avg) if period else 0.0
        clv_prev = float(previous[-1].clv_cohort_avg) if previous else clv

        # Overlay live marketing ROI if available
        live_roi = sources.get("marketing", {}).get("roi")
        if isinstance(live_roi, (int, float)) and live_roi > 0:
            roi = float(live_roi)

        live_util = sources.get("scheduling", {}).get("utilization")
        if isinstance(live_util, (int, float)) and live_util > 0:
            prod = float(live_util) if live_util <= 1 else float(live_util) / 100.0

        defs = [
            (KpiId.REVENUE, "Revenue", rev, rev_prev, "usd", f"${rev:,.0f} in period"),
            (KpiId.RETENTION, "Retention", retention, retention_prev, "ratio", f"{retention:.0%} returning"),
            (KpiId.AVERAGE_REPAIR_ORDER, "Average Repair Order", aro, aro_prev, "usd", f"${aro:,.0f} ARO"),
            (KpiId.CUSTOMER_LIFETIME_VALUE, "Customer Lifetime Value", clv, clv_prev, "usd", f"${clv:,.0f} CLV"),
            (
                KpiId.APPOINTMENT_CONVERSION,
                "Appointment Conversion",
                conv,
                conv_prev,
                "ratio",
                f"{booked}/{offered} booked",
            ),
            (KpiId.MARKETING_ROI, "Marketing ROI", roi, roi_prev, "x", f"{roi:.1f}x return"),
            (
                KpiId.MECHANIC_PRODUCTIVITY,
                "Mechanic Productivity",
                prod,
                prod_prev,
                "ratio",
                f"{prod:.0%} utilization",
            ),
            (
                KpiId.AI_SUCCESS_RATE,
                "AI Success Rate",
                ai_rate,
                ai_prev,
                "ratio",
                f"{ai_ok}/{ai_c} resolved",
            ),
        ]
        out: list[KpiMetric] = []
        for kid, label, cur, prev, unit, detail in defs:
            delta = _pct_delta(cur, prev)
            out.append(
                KpiMetric(
                    id=kid,
                    label=label,
                    value=round(cur, 4) if unit == "ratio" else round(cur, 2),
                    unit=unit,
                    delta_pct=delta,
                    trend=_trend(delta),
                    detail=detail,
                )
            )
        return out

    def _charts(self, period: list[ShopMetricFact], all_facts: list[ShopMetricFact]) -> list[ChartSeries]:
        rev_points = [SeriesPoint(f.day.isoformat(), float(f.revenue)) for f in period]
        conv_points = [
            SeriesPoint(
                f.day.isoformat(),
                round((f.appointments_booked / f.appointments_offered) if f.appointments_offered else 0.0, 3),
            )
            for f in period
        ]
        ai_points = [
            SeriesPoint(
                f.day.isoformat(),
                round((f.ai_resolved / f.ai_conversations) if f.ai_conversations else 0.0, 3),
            )
            for f in period
        ]
        # Monthly revenue rollup from full history
        by_month: dict[str, float] = {}
        for f in all_facts:
            key = f.day.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0.0) + float(f.revenue)
        month_points = [SeriesPoint(k, round(v, 2)) for k, v in sorted(by_month.items())[-6:]]
        return [
            ChartSeries("revenue_daily", "Revenue (daily)", rev_points, "usd"),
            ChartSeries("revenue_monthly", "Revenue (monthly)", month_points, "usd"),
            ChartSeries("appointment_conversion", "Appointment conversion", conv_points, "ratio"),
            ChartSeries("ai_success", "AI success rate", ai_points, "ratio"),
        ]

    def _pull_live_sources(self, shop_id: UUID) -> dict[str, Any]:
        from app.workflows.factory import get_workflow_runtime

        return get_workflow_runtime().coordinator.collect_monitor_snapshots(shop_id)
