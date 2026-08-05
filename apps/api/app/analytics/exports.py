"""Export analytics snapshots and reports to JSON / CSV."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.analytics.enums import ExportFormat
from app.analytics.models import AnalyticsReport, AnalyticsSnapshot, ExportArtifact
from app.analytics.monitoring import AnalyticsMonitor


class ExportService:
    def __init__(self, monitor: AnalyticsMonitor | None = None) -> None:
        self._monitor = monitor

    def export_snapshot(
        self,
        snap: AnalyticsSnapshot,
        *,
        fmt: ExportFormat = ExportFormat.CSV,
    ) -> ExportArtifact:
        if fmt == ExportFormat.JSON:
            body = json.dumps(self._snapshot_dict(snap), indent=2, default=str)
            filename = f"analytics_{snap.shop_id}_{snap.period_end.isoformat()}.json"
            content_type = "application/json"
            rows = len(snap.kpis)
        else:
            body = self._snapshot_csv(snap)
            filename = f"analytics_{snap.shop_id}_{snap.period_end.isoformat()}.csv"
            content_type = "text/csv"
            rows = len(snap.kpis) + sum(len(c.points) for c in snap.charts)
        if self._monitor:
            self._monitor.record_export()
        return ExportArtifact(
            id=uuid4(),
            shop_id=snap.shop_id,
            format=fmt,
            filename=filename,
            content_type=content_type,
            body=body,
            created_at=datetime.now(timezone.utc),
            row_count=rows,
        )

    def export_report(
        self,
        report: AnalyticsReport,
        *,
        fmt: ExportFormat = ExportFormat.JSON,
    ) -> ExportArtifact:
        if fmt == ExportFormat.CSV:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["section", "metric_id", "label", "value", "unit", "delta_pct", "trend"])
            for section in report.sections:
                for m in section.metrics:
                    writer.writerow(
                        [
                            section.id,
                            m.get("id") or m.get("kpi"),
                            m.get("label") or m.get("kpi"),
                            m.get("value") or m.get("shop_value"),
                            m.get("unit", ""),
                            m.get("delta_pct", ""),
                            m.get("trend") or m.get("status", ""),
                        ]
                    )
            body = buf.getvalue()
            content_type = "text/csv"
            filename = f"report_{report.report_type.value}_{report.id}.csv"
            rows = sum(len(s.metrics) for s in report.sections)
        else:
            body = json.dumps(
                {
                    "id": str(report.id),
                    "shop_id": str(report.shop_id),
                    "report_type": report.report_type.value,
                    "title": report.title,
                    "generated_at": report.generated_at.isoformat(),
                    "period_start": report.period_start.isoformat(),
                    "period_end": report.period_end.isoformat(),
                    "summary": report.summary,
                    "sections": [
                        {
                            "id": s.id,
                            "title": s.title,
                            "body": s.body,
                            "metrics": s.metrics,
                        }
                        for s in report.sections
                    ],
                },
                indent=2,
            )
            content_type = "application/json"
            filename = f"report_{report.report_type.value}_{report.id}.json"
            rows = len(report.sections)

        if self._monitor:
            self._monitor.record_export()
        return ExportArtifact(
            id=uuid4(),
            shop_id=report.shop_id,
            format=fmt,
            filename=filename,
            content_type=content_type,
            body=body,
            created_at=datetime.now(timezone.utc),
            report_id=report.id,
            row_count=rows,
        )

    def _snapshot_dict(self, snap: AnalyticsSnapshot) -> dict:
        return {
            "shop_id": str(snap.shop_id),
            "generated_at": snap.generated_at.isoformat(),
            "period_start": snap.period_start.isoformat(),
            "period_end": snap.period_end.isoformat(),
            "version": snap.version,
            "kpis": [
                {
                    "id": k.id.value,
                    "label": k.label,
                    "value": k.value,
                    "unit": k.unit,
                    "delta_pct": k.delta_pct,
                    "trend": k.trend.value,
                    "target": k.target,
                    "benchmark": k.benchmark,
                    "vs_benchmark_pct": k.vs_benchmark_pct,
                    "detail": k.detail,
                }
                for k in snap.kpis
            ],
            "charts": [
                {
                    "id": c.id,
                    "title": c.title,
                    "unit": c.unit,
                    "points": [{"label": p.label, "value": p.value, "secondary": p.secondary} for p in c.points],
                }
                for c in snap.charts
            ],
            "forecasts": [
                {
                    "kpi": f.kpi.value,
                    "horizon_days": f.horizon_days,
                    "method": f.method,
                    "summary": f.summary,
                    "points": [
                        {"period": p.period, "predicted": p.predicted, "low": p.low, "high": p.high}
                        for p in f.points
                    ],
                }
                for f in snap.forecasts
            ],
            "benchmarks": [
                {
                    "kpi": b.kpi.value,
                    "label": b.label,
                    "shop_value": b.shop_value,
                    "industry_avg": b.industry_avg,
                    "top_quartile": b.top_quartile,
                    "unit": b.unit,
                    "status": b.status,
                }
                for b in snap.benchmarks
            ],
        }

    def _snapshot_csv(self, snap: AnalyticsSnapshot) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "section",
                "id",
                "label",
                "value",
                "unit",
                "delta_pct",
                "trend",
                "benchmark",
                "vs_benchmark_pct",
                "detail",
            ]
        )
        for k in snap.kpis:
            writer.writerow(
                [
                    "kpi",
                    k.id.value,
                    k.label,
                    k.value,
                    k.unit,
                    k.delta_pct,
                    k.trend.value,
                    k.benchmark,
                    k.vs_benchmark_pct,
                    k.detail,
                ]
            )
        for b in snap.benchmarks:
            writer.writerow(
                [
                    "benchmark",
                    b.kpi.value,
                    b.label,
                    b.shop_value,
                    b.unit,
                    "",
                    b.status,
                    b.industry_avg,
                    "",
                    f"top={b.top_quartile}",
                ]
            )
        for c in snap.charts:
            for p in c.points:
                writer.writerow(["chart", c.id, p.label, p.value, c.unit or "", "", "", "", "", c.title])
        return buf.getvalue()
