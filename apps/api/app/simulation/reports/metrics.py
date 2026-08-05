"""Aggregate SimulationRunResult lists into SimulationMetrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.simulation.models import SimulationMetrics, SimulationRunResult


def compute_metrics(results: list[SimulationRunResult]) -> SimulationMetrics:
    total = len(results)
    if total == 0:
        return SimulationMetrics()

    successful = sum(1 for r in results if r.success)
    decisions = [d for r in results for d in r.decisions]
    plugins = [p for r in results for p in r.plugins]

    accurate = sum(1 for d in decisions if d.accurate)
    conf_sum = sum(d.confidence for d in decisions)
    plugin_fails = sum(1 for p in plugins if not p.success)

    appt_eligible = [r for r in results if r.appointment is not None or r.appointment_converted]
    appt_converted = sum(1 for r in results if r.appointment_converted)
    # Prefer appointment.booked when present
    booked = sum(
        1
        for r in results
        if (r.appointment and r.appointment.booked) or r.appointment_converted
    )
    appt_denom = max(1, len(appt_eligible) if appt_eligible else total)

    retentions = [r.retention_prediction for r in results if r.retention_prediction is not None]

    by_scenario: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "success": 0})
    for r in results:
        key = r.scenario.value
        by_scenario[key]["total"] += 1
        if r.success:
            by_scenario[key]["success"] += 1
    for key, bucket in by_scenario.items():
        bucket["success_rate"] = round(bucket["success"] / max(1, bucket["total"]), 4)

    return SimulationMetrics(
        total_runs=total,
        successful_runs=successful,
        workflow_success_rate=round(successful / total, 4),
        ai_decision_accuracy=round(accurate / max(1, len(decisions)), 4),
        decision_confidence_avg=round(conf_sum / max(1, len(decisions)), 4),
        plugin_failure_rate=round(plugin_fails / max(1, len(plugins)), 4),
        appointment_conversion_rate=round(booked / appt_denom, 4),
        revenue_opportunity_detection_rate=round(
            sum(1 for r in results if r.revenue_opportunity_detected) / total, 4
        ),
        customer_retention_prediction_avg=round(
            (sum(retentions) / len(retentions)) if retentions else 0.0, 4
        ),
        human_escalation_rate=round(sum(1 for r in results if r.escalated) / total, 4),
        by_scenario=dict(by_scenario),
    )
