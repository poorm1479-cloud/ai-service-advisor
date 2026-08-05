"""Report generation from analytics snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.analytics.enums import ReportType
from app.analytics.models import AnalyticsReport, AnalyticsSnapshot, ReportSection
from app.analytics.monitoring import AnalyticsMonitor


class ReportBuilder:
    def __init__(self, monitor: AnalyticsMonitor | None = None) -> None:
        self._monitor = monitor

    def build(
        self,
        snap: AnalyticsSnapshot,
        *,
        report_type: ReportType = ReportType.FULL,
        title: str | None = None,
    ) -> AnalyticsReport:
        if self._monitor:
            self._monitor.record_report(report_type.value)

        sections: list[ReportSection] = []
        if report_type in {ReportType.FULL, ReportType.EXECUTIVE_SUMMARY, ReportType.REVENUE}:
            sections.append(self._kpi_section(snap, "revenue", "Revenue & ARO", {"revenue", "average_repair_order", "customer_lifetime_value"}))
        if report_type in {ReportType.FULL, ReportType.EXECUTIVE_SUMMARY, ReportType.RETENTION}:
            sections.append(self._kpi_section(snap, "retention", "Retention & Conversion", {"retention", "appointment_conversion"}))
        if report_type in {ReportType.FULL, ReportType.MARKETING}:
            sections.append(self._kpi_section(snap, "marketing", "Marketing", {"marketing_roi"}))
        if report_type in {ReportType.FULL, ReportType.OPERATIONS}:
            sections.append(self._kpi_section(snap, "operations", "Operations", {"mechanic_productivity"}))
        if report_type in {ReportType.FULL, ReportType.AI_PERFORMANCE}:
            sections.append(self._kpi_section(snap, "ai", "AI Performance", {"ai_success_rate"}))
        if report_type in {ReportType.FULL, ReportType.EXECUTIVE_SUMMARY}:
            sections.append(self._benchmark_section(snap))
            sections.append(self._forecast_section(snap))

        summary = self._summary(snap, report_type)
        return AnalyticsReport(
            id=uuid4(),
            shop_id=snap.shop_id,
            report_type=report_type,
            title=title or f"{report_type.value.replace('_', ' ').title()} Report",
            generated_at=datetime.now(timezone.utc),
            period_start=snap.period_start,
            period_end=snap.period_end,
            sections=sections,
            summary=summary,
            metadata={"snapshot_version": snap.version},
        )

    def _kpi_section(
        self,
        snap: AnalyticsSnapshot,
        sid: str,
        title: str,
        ids: set[str],
    ) -> ReportSection:
        metrics = []
        lines = []
        for k in snap.kpis:
            if k.id.value not in ids:
                continue
            metrics.append(
                {
                    "id": k.id.value,
                    "label": k.label,
                    "value": k.value,
                    "unit": k.unit,
                    "delta_pct": k.delta_pct,
                    "trend": k.trend.value,
                }
            )
            lines.append(f"- {k.label}: {k.detail or k.value} ({k.delta_pct:+.1f}% vs prior)")
        body = "\n".join(lines) if lines else "No metrics in this section."
        return ReportSection(id=sid, title=title, body=body, metrics=metrics)

    def _benchmark_section(self, snap: AnalyticsSnapshot) -> ReportSection:
        lines = []
        metrics = []
        for b in snap.benchmarks:
            lines.append(
                f"- {b.label}: shop={b.shop_value:.2f} vs industry={b.industry_avg:.2f} "
                f"(top={b.top_quartile:.2f}) → {b.status}"
            )
            metrics.append(
                {
                    "kpi": b.kpi.value,
                    "shop_value": b.shop_value,
                    "industry_avg": b.industry_avg,
                    "top_quartile": b.top_quartile,
                    "status": b.status,
                }
            )
        return ReportSection(
            id="benchmarks",
            title="Benchmarks",
            body="\n".join(lines) or "No benchmarks.",
            metrics=metrics,
        )

    def _forecast_section(self, snap: AnalyticsSnapshot) -> ReportSection:
        lines = []
        metrics = []
        for f in snap.forecasts:
            lines.append(f"- {f.kpi.value}: {f.summary}")
            if f.points:
                lines.append(
                    f"  Next day ~{f.points[0].predicted:.2f} "
                    f"(band {f.points[0].low:.2f}–{f.points[0].high:.2f})"
                )
            metrics.append(
                {
                    "kpi": f.kpi.value,
                    "horizon_days": f.horizon_days,
                    "method": f.method,
                    "summary": f.summary,
                }
            )
        return ReportSection(
            id="forecast",
            title="Forecast",
            body="\n".join(lines) or "No forecasts.",
            metrics=metrics,
        )

    def _summary(self, snap: AnalyticsSnapshot, report_type: ReportType) -> str:
        ahead = sum(1 for b in snap.benchmarks if b.status == "ahead")
        behind = sum(1 for b in snap.benchmarks if b.status == "behind")
        return (
            f"{report_type.value.replace('_', ' ').title()} for "
            f"{snap.period_start.isoformat()} → {snap.period_end.isoformat()}. "
            f"Benchmarks: {ahead} ahead, {behind} behind industry."
        )
