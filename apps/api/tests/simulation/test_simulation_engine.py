"""Phase 12 — Auto Repair Simulation Engine tests."""

from __future__ import annotations

import pytest

from app.simulation.engine import SimulationEngine, run_simulations
from app.simulation.generators import EntityGenerator
from app.simulation.models import ScenarioKind
from app.simulation.reports import build_report, compute_metrics, render_summary_markdown
from app.simulation.scenarios import SCENARIO_REGISTRY, all_scenarios
from app.workflows.factory import build_workflow_runtime, ensure_seeded, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    yield
    reset_workflow_runtime()


@pytest.fixture
async def runtime():
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    await ensure_seeded(rt)
    return rt


def test_scenario_registry_complete():
    assert len(SCENARIO_REGISTRY) == 6
    assert len(all_scenarios()) == 6
    assert set(SCENARIO_REGISTRY.keys()) == set(ScenarioKind)


def test_entity_generator_produces_entities():
    gen = EntityGenerator(seed=1)
    customer = gen.customer()
    vehicle = gen.vehicle(customer)
    convo = gen.conversation(customer=customer, channel="phone", body="brakes", intent="maintenance")
    repair = gen.repair_request(customer=customer, vehicle=vehicle, complaint="brake noise")
    appt = gen.appointment(customer=customer, vehicle=vehicle, repair_type=repair.recommended_service)
    insp = gen.inspection(vehicle)
    est = gen.estimate(customer=customer, amount=200)
    pay = gen.payment(amount=200)
    assert customer.phone.startswith("+1")
    assert len(vehicle.vin) == 17
    assert convo.body == "brakes"
    assert repair.recommended_service == "brake_inspection"
    assert appt.repair_type == "brake_inspection"
    assert insp.findings
    assert est.amount == 200
    assert pay.amount == 200


@pytest.mark.asyncio
async def test_each_scenario_runs(runtime):
    engine = SimulationEngine(seed=7, runtime=runtime)
    for kind, cls in SCENARIO_REGISTRY.items():
        result = await engine.run_one(cls())
        assert result.scenario == kind
        assert result.customer is not None or kind == ScenarioKind.WALK_IN
        assert result.vehicle is not None
        assert len(result.decisions) >= 1
        assert len(result.events) >= 1
        assert len(result.workflow_names) >= 1
        assert result.success is True


@pytest.mark.asyncio
async def test_run_10_simulations(runtime):
    engine = SimulationEngine(seed=42, runtime=runtime)
    report = await engine.run(10)
    assert report.run_count == 10
    assert report.metrics.total_runs == 10
    assert report.metrics.workflow_success_rate >= 0.8
    assert 0 <= report.metrics.ai_decision_accuracy <= 1
    assert 0 <= report.metrics.decision_confidence_avg <= 1
    assert 0 <= report.metrics.plugin_failure_rate <= 1
    assert report.workflow_performance
    assert "total_estimated_revenue" in report.revenue_impact
    md = render_summary_markdown(report)
    assert "Workflow Success Rate" in md
    assert "Revenue Impact" in md


@pytest.mark.asyncio
async def test_run_100_simulations(runtime):
    engine = SimulationEngine(seed=99, runtime=runtime)
    report = await engine.run_batch(100)
    assert report.run_count == 100
    assert report.metrics.successful_runs >= 80
    assert len(report.metrics.by_scenario) == 6


@pytest.mark.asyncio
async def test_run_simulations_helper():
    report = await run_simulations(10, seed=3, scenarios=[ScenarioKind.MAINTENANCE_REMINDER])
    assert report.run_count == 10
    assert all(r.scenario == ScenarioKind.MAINTENANCE_REMINDER for r in report.runs)


def test_metrics_empty():
    m = compute_metrics([])
    assert m.total_runs == 0
    report = build_report([])
    assert report.run_count == 0
