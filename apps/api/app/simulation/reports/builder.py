"""Build SimulationReport artifacts from run results."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.simulation.models import SimulationReport, SimulationRunResult
from app.simulation.reports.metrics import compute_metrics


def build_report(results: list[SimulationRunResult]) -> SimulationReport:
    metrics = compute_metrics(results)
    errors: list[str] = []
    failed_steps: list[dict[str, Any]] = []
    ai_decisions: list[dict[str, Any]] = []
    workflow_counter: Counter[str] = Counter()
    workflow_success: defaultdict[str, list[bool]] = defaultdict(list)
    revenue_total = 0.0
    revenue_detected = 0.0

    for r in results:
        errors.extend(r.errors)
        for step in r.workflow_steps:
            if step.status.lower() in {"failed", "error"}:
                failed_steps.append(
                    {
                        "run_id": str(r.run_id),
                        "scenario": r.scenario.value,
                        "step": step.name,
                        "error": step.error,
                    }
                )
        for d in r.decisions:
            ai_decisions.append(
                {
                    "run_id": str(r.run_id),
                    "scenario": r.scenario.value,
                    "decision_type": d.decision_type,
                    "confidence": d.confidence,
                    "accurate": d.accurate,
                    "summary": d.summary,
                }
            )
        for name in r.workflow_names:
            workflow_counter[name] += 1
            workflow_success[name].append(r.success)

        amount = 0.0
        if r.estimate:
            amount = float(r.estimate.amount)
        elif r.repair:
            amount = float(r.repair.estimated_cost)
        elif r.payment:
            amount = float(r.payment.amount)
        revenue_total += amount
        if r.revenue_opportunity_detected:
            revenue_detected += amount

    workflow_performance = [
        {
            "workflow": name,
            "runs": count,
            "success_rate": round(
                sum(1 for ok in workflow_success[name] if ok) / max(1, len(workflow_success[name])),
                4,
            ),
        }
        for name, count in workflow_counter.most_common()
    ]

    return SimulationReport(
        report_id=uuid4(),
        generated_at=datetime.now(timezone.utc),
        run_count=len(results),
        metrics=metrics,
        summary="",
        workflow_performance=workflow_performance,
        revenue_impact={
            "total_estimated_revenue": round(revenue_total, 2),
            "opportunity_linked_revenue": round(revenue_detected, 2),
            "opportunity_share": round(revenue_detected / revenue_total, 4) if revenue_total else 0.0,
            "opportunities_detected": sum(1 for r in results if r.revenue_opportunity_detected),
        },
        errors=errors[:200],
        failed_steps=failed_steps[:200],
        ai_decisions=ai_decisions,
        runs=results,
    )


def render_summary_markdown(report: SimulationReport) -> str:
    m = report.metrics
    lines = [
        "# Simulation Summary",
        "",
        report.summary or f"{report.run_count} simulation runs.",
        "",
        "## Metrics",
        f"- Workflow Success Rate: {m.workflow_success_rate:.2%}",
        f"- AI Decision Accuracy: {m.ai_decision_accuracy:.2%}",
        f"- Decision Confidence (avg): {m.decision_confidence_avg:.3f}",
        f"- Plugin Failure Rate: {m.plugin_failure_rate:.2%}",
        f"- Appointment Conversion Rate: {m.appointment_conversion_rate:.2%}",
        f"- Revenue Opportunity Detection: {m.revenue_opportunity_detection_rate:.2%}",
        f"- Customer Retention Prediction (avg): {m.customer_retention_prediction_avg:.3f}",
        f"- Human Escalation Rate: {m.human_escalation_rate:.2%}",
        "",
        "## Workflow Performance",
    ]
    for row in report.workflow_performance:
        lines.append(
            f"- {row['workflow']}: {row['runs']} runs, success={row['success_rate']:.2%}"
        )
    lines.extend(
        [
            "",
            "## Revenue Impact",
            f"- Total estimated revenue: ${report.revenue_impact.get('total_estimated_revenue', 0):,.2f}",
            f"- Opportunity-linked revenue: ${report.revenue_impact.get('opportunity_linked_revenue', 0):,.2f}",
            "",
            f"## Errors ({len(report.errors)})",
        ]
    )
    for err in report.errors[:20]:
        lines.append(f"- {err}")
    if not report.errors:
        lines.append("- None")
    lines.extend(["", f"## Failed Steps ({len(report.failed_steps)})"])
    for step in report.failed_steps[:20]:
        lines.append(f"- {step.get('step')}: {step.get('error')}")
    if not report.failed_steps:
        lines.append("- None")
    lines.extend(["", f"## AI Decisions (sample {min(10, len(report.ai_decisions))})"])
    for d in report.ai_decisions[:10]:
        lines.append(
            f"- {d['decision_type']} conf={d['confidence']:.2f} accurate={d['accurate']}: {d['summary']}"
        )
    return "\n".join(lines)
