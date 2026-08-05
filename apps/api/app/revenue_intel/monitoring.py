"""Revenue intelligence monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RevenueIntelMonitor:
    nightly_runs: int = 0
    opportunities_generated: int = 0
    customers_analyzed: int = 0
    failures: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def record_nightly(self, *, customers: int, opportunities: int, kinds: dict[str, int]) -> None:
        self.nightly_runs += 1
        self.customers_analyzed += customers
        self.opportunities_generated += opportunities
        for k, v in kinds.items():
            self.by_kind[k] = self.by_kind.get(k, 0) + v

    def record_failure(self) -> None:
        self.failures += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "nightly_runs": self.nightly_runs,
            "opportunities_generated": self.opportunities_generated,
            "customers_analyzed": self.customers_analyzed,
            "failures": self.failures,
            "by_kind": dict(self.by_kind),
        }
