"""Analytics store port + in-memory implementation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID

from app.analytics.models import AnalyticsReport, AnalyticsSnapshot, ExportArtifact, ShopMetricFact


class AnalyticsStorePort(Protocol):
    def save_fact(self, fact: ShopMetricFact) -> ShopMetricFact: ...

    def list_facts(
        self,
        shop_id: UUID,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShopMetricFact]: ...

    def save_snapshot(self, snap: AnalyticsSnapshot) -> AnalyticsSnapshot: ...

    def get_snapshot(self, shop_id: UUID) -> AnalyticsSnapshot | None: ...

    def save_report(self, report: AnalyticsReport) -> AnalyticsReport: ...

    def get_report(self, shop_id: UUID, report_id: UUID) -> AnalyticsReport | None: ...

    def list_reports(self, shop_id: UUID, *, limit: int = 50) -> list[AnalyticsReport]: ...

    def save_export(self, artifact: ExportArtifact) -> ExportArtifact: ...

    def get_export(self, shop_id: UUID, export_id: UUID) -> ExportArtifact | None: ...

    def list_exports(self, shop_id: UUID, *, limit: int = 50) -> list[ExportArtifact]: ...


class InMemoryAnalyticsStore:
    def __init__(self) -> None:
        self._facts: dict[tuple[UUID, date], ShopMetricFact] = {}
        self._snapshots: dict[UUID, AnalyticsSnapshot] = {}
        self._reports: dict[UUID, AnalyticsReport] = {}
        self._exports: dict[UUID, ExportArtifact] = {}

    def save_fact(self, fact: ShopMetricFact) -> ShopMetricFact:
        self._facts[(fact.shop_id, fact.day)] = fact
        return fact

    def list_facts(
        self,
        shop_id: UUID,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[ShopMetricFact]:
        rows = [f for (sid, _), f in self._facts.items() if sid == shop_id]
        if start:
            rows = [f for f in rows if f.day >= start]
        if end:
            rows = [f for f in rows if f.day <= end]
        return sorted(rows, key=lambda f: f.day)

    def save_snapshot(self, snap: AnalyticsSnapshot) -> AnalyticsSnapshot:
        self._snapshots[snap.shop_id] = snap
        return snap

    def get_snapshot(self, shop_id: UUID) -> AnalyticsSnapshot | None:
        return self._snapshots.get(shop_id)

    def save_report(self, report: AnalyticsReport) -> AnalyticsReport:
        self._reports[report.id] = report
        return report

    def get_report(self, shop_id: UUID, report_id: UUID) -> AnalyticsReport | None:
        r = self._reports.get(report_id)
        if r is None or r.shop_id != shop_id:
            return None
        return r

    def list_reports(self, shop_id: UUID, *, limit: int = 50) -> list[AnalyticsReport]:
        rows = [r for r in self._reports.values() if r.shop_id == shop_id]
        rows.sort(key=lambda r: r.generated_at, reverse=True)
        return rows[:limit]

    def save_export(self, artifact: ExportArtifact) -> ExportArtifact:
        self._exports[artifact.id] = artifact
        return artifact

    def get_export(self, shop_id: UUID, export_id: UUID) -> ExportArtifact | None:
        a = self._exports.get(export_id)
        if a is None or a.shop_id != shop_id:
            return None
        return a

    def list_exports(self, shop_id: UUID, *, limit: int = 50) -> list[ExportArtifact]:
        rows = [a for a in self._exports.values() if a.shop_id == shop_id]
        rows.sort(key=lambda a: a.created_at, reverse=True)
        return rows[:limit]
