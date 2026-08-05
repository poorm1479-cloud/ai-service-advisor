"""Auto Repair Simulation Engine — Phase 12.

Orchestrates synthetic automotive repair-shop simulations without changing
production business logic, workflows, or plugins.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import UUID, uuid4

from app.simulation.generators import EntityGenerator
from app.simulation.models import ScenarioKind, SimulationReport, SimulationRunResult
from app.simulation.reports.builder import build_report
from app.simulation.scenarios import SCENARIO_REGISTRY, all_scenarios
from app.simulation.scenarios.base import BaseScenario, ScenarioContext
from app.workflows.factory import WorkflowRuntime, build_workflow_runtime, ensure_seeded
from app.workflows.store import InMemoryWorkflowStore


class SimulationEngine:
    """Run N automotive repair simulations and collect metrics/reports."""

    def __init__(
        self,
        *,
        seed: int | None = 42,
        shop_id: UUID | None = None,
        scenarios: Sequence[ScenarioKind] | None = None,
        runtime: WorkflowRuntime | None = None,
    ) -> None:
        self.seed = seed
        self.shop_id = shop_id or uuid4()
        self.scenario_kinds = list(scenarios) if scenarios else list(ScenarioKind)
        self._runtime = runtime
        self._generator = EntityGenerator(seed=seed)

    async def _get_runtime(self) -> WorkflowRuntime:
        if self._runtime is None:
            self._runtime = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
            await ensure_seeded(self._runtime)
        return self._runtime

    def _scenario_cycle(self) -> Iterable[BaseScenario]:
        instances = [
            SCENARIO_REGISTRY[kind]()
            for kind in self.scenario_kinds
            if kind in SCENARIO_REGISTRY
        ]
        if not instances:
            instances = all_scenarios()
        return itertools.cycle(instances)

    async def run_one(self, scenario: BaseScenario | None = None) -> SimulationRunResult:
        runtime = await self._get_runtime()
        sc = scenario or next(iter(self._scenario_cycle()))
        ctx = ScenarioContext(
            runtime=runtime,
            shop_id=self.shop_id,
            generator=self._generator,
            scenario=sc.kind,
        )
        try:
            return await sc.run(ctx)
        except Exception as exc:  # noqa: BLE001 — collect failure for report
            ctx.result.errors.append(str(exc))
            ctx.result.notes.append(f"Unhandled simulation error: {exc}")
            return ctx.finish(success=False)

    async def run(self, count: int = 10) -> SimulationReport:
        """Run `count` simulations (supports 10 / 100 / 1000)."""
        if count < 1:
            raise ValueError("count must be >= 1")
        started = datetime.now(timezone.utc)
        results: list[SimulationRunResult] = []
        cycle = self._scenario_cycle()
        for _ in range(count):
            results.append(await self.run_one(next(cycle)))
        report = build_report(results)
        report.generated_at = datetime.now(timezone.utc)
        report.summary = (
            f"Auto Repair Simulation completed {len(results)} runs "
            f"across {len(self.scenario_kinds)} scenario kinds "
            f"(started {started.isoformat()})."
        )
        return report

    async def run_batch(self, size: int) -> SimulationReport:
        """Alias for supported batch sizes."""
        if size not in (10, 100, 1000):
            # Still allow custom sizes; documented sizes are preferred.
            pass
        return await self.run(size)


async def run_simulations(
    count: int = 10,
    *,
    seed: int | None = 42,
    scenarios: Sequence[ScenarioKind] | None = None,
) -> SimulationReport:
    """Convenience entry point for CLI / tests."""
    engine = SimulationEngine(seed=seed, scenarios=scenarios)
    return await engine.run(count)
