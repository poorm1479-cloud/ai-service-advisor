"""Analytics monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalyticsMonitor:
    snapshots: int = 0
    reports: int = 0
    exports: int = 0
    forecasts: int = 0
    facts_ingested: int = 0
    by_report_type: dict[str, int] = field(default_factory=dict)

    def record_snapshot(self) -> None:
        self.snapshots += 1

    def record_report(self, report_type: str) -> None:
        self.reports += 1
        self.by_report_type[report_type] = self.by_report_type.get(report_type, 0) + 1

    def record_export(self) -> None:
        self.exports += 1

    def record_forecast(self) -> None:
        self.forecasts += 1

    def record_facts(self, n: int) -> None:
        self.facts_ingested += n

    def snapshot(self) -> dict[str, object]:
        return {
            "snapshots": self.snapshots,
            "reports": self.reports,
            "exports": self.exports,
            "forecasts": self.forecasts,
            "facts_ingested": self.facts_ingested,
            "by_report_type": dict(self.by_report_type),
        }
