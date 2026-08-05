"""Time-series forecast for analytics KPIs."""

from __future__ import annotations

from datetime import date, timedelta

from app.analytics.enums import KpiId
from app.analytics.models import ForecastPoint, ForecastResult, ShopMetricFact
from app.analytics.monitoring import AnalyticsMonitor


class ForecastEngine:
    """Simple Holt-style linear trend + seasonal weekend dampening (no external deps)."""

    def __init__(self, monitor: AnalyticsMonitor | None = None) -> None:
        self._monitor = monitor

    def forecast_revenue(
        self,
        facts: list[ShopMetricFact],
        *,
        horizon_days: int = 30,
    ) -> ForecastResult:
        series = [float(f.revenue) for f in facts]
        return self._forecast_series(
            KpiId.REVENUE,
            series,
            facts[-1].day if facts else date.today(),
            horizon_days=horizon_days,
            unit_label="revenue",
        )

    def forecast_kpi_series(
        self,
        kpi: KpiId,
        values: list[float],
        last_day: date,
        *,
        horizon_days: int = 30,
    ) -> ForecastResult:
        return self._forecast_series(kpi, values, last_day, horizon_days=horizon_days)

    def _forecast_series(
        self,
        kpi: KpiId,
        series: list[float],
        last_day: date,
        *,
        horizon_days: int,
        unit_label: str | None = None,
    ) -> ForecastResult:
        if self._monitor:
            self._monitor.record_forecast()
        if len(series) < 3:
            base = series[-1] if series else 0.0
            points = [
                ForecastPoint(
                    period=(last_day + timedelta(days=i + 1)).isoformat(),
                    predicted=base,
                    low=base * 0.9,
                    high=base * 1.1,
                )
                for i in range(horizon_days)
            ]
            return ForecastResult(
                kpi=kpi,
                horizon_days=horizon_days,
                method="constant",
                points=points,
                summary=f"Insufficient history; holding {unit_label or kpi.value} flat.",
            )

        # Linear regression on last N points
        n = min(len(series), 60)
        ys = series[-n:]
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        denom = sum((x - x_mean) ** 2 for x in xs) or 1.0
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denom
        intercept = y_mean - slope * x_mean
        residual = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
        sigma = (sum(r * r for r in residual) / max(1, n - 2)) ** 0.5

        points: list[ForecastPoint] = []
        for i in range(1, horizon_days + 1):
            x = n - 1 + i
            pred = intercept + slope * x
            day = last_day + timedelta(days=i)
            if day.weekday() >= 5:
                pred *= 0.6
            pred = max(0.0, pred)
            band = max(sigma * 1.64, pred * 0.08)
            points.append(
                ForecastPoint(
                    period=day.isoformat(),
                    predicted=round(pred, 2),
                    low=round(max(0.0, pred - band), 2),
                    high=round(pred + band, 2),
                )
            )

        trend = "rising" if slope > 0 else "softening" if slope < 0 else "stable"
        return ForecastResult(
            kpi=kpi,
            horizon_days=horizon_days,
            method="linear_trend_weekend",
            points=points,
            summary=f"{kpi.value} outlook {trend} over {horizon_days} days (slope={slope:.2f}/day).",
        )
