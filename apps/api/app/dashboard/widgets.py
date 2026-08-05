"""Dashboard widget builders — read-only presentation structures."""

from __future__ import annotations

from typing import Any

from app.dashboard.metrics import performance_from_sources, safe_int
from app.dashboard.models import DashboardWidget, MetricPoint, QueueItem


def build_widgets(sources: dict[str, Any]) -> list[DashboardWidget]:
    voice = sources.get("voice") or {}
    workflow = sources.get("workflow") or {}
    revenue = sources.get("revenue") or {}
    scheduling = sources.get("scheduling") or {}
    conversation = sources.get("conversation") or {}
    inspection = sources.get("inspection") or {}
    executive = sources.get("executive") or {}
    live = executive.get("live") or {}
    perf = performance_from_sources(sources)

    widgets: list[DashboardWidget] = []

    widgets.append(
        DashboardWidget(
            id="ai_employee_summary",
            title="AI Employee Summary",
            kind="summary",
            summary="AI activity across voice, conversations, and workflows",
            metrics=[
                MetricPoint("ai_conversations", "AI conversations", safe_int(live.get("ai_conversations") or conversation.get("open_conversations"))),
                MetricPoint("call_volume", "Calls", safe_int(voice.get("call_volume") or voice.get("calls_started"))),
                MetricPoint("ai_resolution", "AI resolution", f"{perf['ai_resolution_rate']*100:.0f}%", tone="good"),
                MetricPoint("escalations", "Human escalations", safe_int(live.get("human_escalations") or int(perf["human_transfer_rate"] * max(1, perf["call_volume"])))),
            ],
        )
    )

    appt_items = []
    for i, raw in enumerate((scheduling.get("appointments") or scheduling.get("items") or [])[:8]):
        if isinstance(raw, dict):
            appt_items.append(
                QueueItem(
                    id=str(raw.get("id") or i),
                    title=str(raw.get("title") or raw.get("customer") or "Appointment"),
                    subtitle=str(raw.get("start") or raw.get("time") or ""),
                    status=str(raw.get("status") or "scheduled"),
                    href="/dashboard/appointments",
                )
            )
    if not appt_items:
        count = safe_int(scheduling.get("appointments_today") or live.get("appointments_today"))
        appt_items.append(
            QueueItem(
                id="appt-today",
                title=f"{count} appointment(s) today",
                subtitle="From scheduling snapshot",
                status="scheduled",
                href="/dashboard/appointments",
            )
        )
    widgets.append(
        DashboardWidget(
            id="todays_appointments",
            title="Today's Appointments",
            kind="queue",
            items=appt_items,
            metrics=[
                MetricPoint(
                    "appointments_today",
                    "Today",
                    safe_int(scheduling.get("appointments_today") or live.get("appointments_today")),
                )
            ],
        )
    )

    rev_items: list[QueueItem] = []
    for i, opp in enumerate((revenue.get("items") or [])[:8]):
        if isinstance(opp, dict):
            rev_items.append(
                QueueItem(
                    id=str(opp.get("id") or i),
                    title=str(opp.get("title") or opp.get("reason") or opp.get("kind") or "Opportunity"),
                    subtitle=str(opp.get("expected_revenue") or opp.get("amount") or ""),
                    status=str(opp.get("status") or "open"),
                    priority="high",
                    href="/dashboard",
                    meta=opp,
                )
            )
    if not rev_items:
        n = safe_int(revenue.get("open_opportunities"))
        rev_items.append(
            QueueItem(
                id="rev-open",
                title=f"{n} open revenue opportunity(ies)",
                status="open",
                href="/dashboard",
            )
        )
    widgets.append(
        DashboardWidget(
            id="revenue_opportunities",
            title="Revenue Opportunities",
            kind="queue",
            items=rev_items,
        )
    )

    followups: list[QueueItem] = []
    for i, c in enumerate((conversation.get("items") or [])[:8]):
        followups.append(
            QueueItem(
                id=str(c.get("id") or i),
                title=f"Conversation {str(c.get('id') or '')[:8]}",
                subtitle=str(c.get("channel") or "channel"),
                status=str(c.get("status") or "open"),
                href="/dashboard/ai-inbox",
            )
        )
    if not followups:
        followups.append(
            QueueItem(
                id="follow-empty",
                title="No open follow-ups in snapshot",
                status="idle",
                href="/dashboard/ai-inbox",
            )
        )
    widgets.append(
        DashboardWidget(
            id="customer_followup_queue",
            title="Customer Follow-up Queue",
            kind="queue",
            items=followups,
        )
    )

    approvals: list[QueueItem] = []
    for a in (inspection.get("pending_approvals") or [])[:8]:
        approvals.append(
            QueueItem(
                id=str(a.get("id")),
                title="Inspection approval",
                subtitle=f"{a.get('finding_count', 0)} finding(s)",
                status=str(a.get("status") or "pending"),
                priority="high",
                href="/dashboard/workflows",
            )
        )
    if not approvals:
        approvals.append(
            QueueItem(id="appr-empty", title="No pending approvals", status="clear", priority="low")
        )
    widgets.append(
        DashboardWidget(
            id="approval_queue",
            title="Approval Queue",
            kind="queue",
            items=approvals,
        )
    )

    esc_rate = perf["human_transfer_rate"]
    esc_items = [
        QueueItem(
            id="esc-voice",
            title="Voice human transfers",
            subtitle=f"Rate {esc_rate*100:.0f}%",
            status="watch" if esc_rate > 0.2 else "ok",
            priority="high" if esc_rate > 0.35 else "normal",
            href="/dashboard/calls",
        )
    ]
    if safe_int(live.get("human_escalations")):
        esc_items.append(
            QueueItem(
                id="esc-live",
                title=f"{live.get('human_escalations')} live escalation(s)",
                status="open",
                priority="urgent",
                href="/dashboard/calls",
            )
        )
    widgets.append(
        DashboardWidget(
            id="ai_escalation_queue",
            title="AI Escalation Queue",
            kind="queue",
            items=esc_items,
        )
    )

    wf_items: list[QueueItem] = []
    for r in (workflow.get("recent_runs") or [])[:8]:
        wf_items.append(
            QueueItem(
                id=str(r.get("id")),
                title=str(r.get("name") or "Workflow"),
                status=str(r.get("status") or "unknown"),
                href="/dashboard/workflows",
            )
        )
    if not wf_items:
        wf_items.append(QueueItem(id="wf-empty", title="No recent workflow runs", status="idle"))
    widgets.append(
        DashboardWidget(
            id="workflow_monitor",
            title="Workflow Monitor",
            kind="monitor",
            items=wf_items,
            metrics=[
                MetricPoint("runs", "Runs", safe_int(workflow.get("run_count"))),
                MetricPoint("pending", "Pending", safe_int(workflow.get("pending")), tone="warn"),
                MetricPoint("failed", "Failed", safe_int(workflow.get("failed")), tone="bad"),
            ],
        )
    )

    widgets.append(
        DashboardWidget(
            id="performance_metrics",
            title="Performance Metrics",
            kind="metrics",
            metrics=[
                MetricPoint("workflow_success", "Workflow success", f"{perf['workflow_success_rate']*100:.0f}%", tone="good"),
                MetricPoint("ai_resolution", "AI resolution", f"{perf['ai_resolution_rate']*100:.0f}%"),
                MetricPoint("transfer_rate", "Human transfer", f"{perf['human_transfer_rate']*100:.0f}%"),
                MetricPoint("response_ms", "Avg response", perf["average_response_time_ms"], unit="ms"),
                MetricPoint("rev_opps", "Revenue opps", perf["open_revenue_opportunities"]),
                MetricPoint("appts", "Appointments today", perf["appointments_today"]),
                MetricPoint(
                    "retention",
                    "Retention rate",
                    f"{perf.get('customer_retention_rate', 0)*100:.0f}%",
                    tone="good",
                ),
                MetricPoint("lost_risk", "Lost customer risk", perf.get("lost_customer_risk", 0)),
                MetricPoint(
                    "svc_recs",
                    "Service recommendations",
                    perf.get("service_recommendations", 0),
                ),
            ],
        )
    )

    campaign = perf.get("campaign_performance") or {}
    widgets.append(
        DashboardWidget(
            id="retention_intelligence",
            title="Customer Retention & Revenue Intelligence",
            kind="metrics",
            metrics=[
                MetricPoint(
                    "retention_rate",
                    "Customer Retention Rate",
                    f"{perf.get('customer_retention_rate', 0)*100:.0f}%",
                ),
                MetricPoint(
                    "lost_risk",
                    "Lost Customer Risk",
                    perf.get("lost_customer_risk", 0),
                ),
                MetricPoint(
                    "rev_opps20",
                    "Revenue Opportunities",
                    perf.get("revenue_opportunities", perf.get("open_revenue_opportunities", 0)),
                ),
                MetricPoint(
                    "recovered",
                    "Recovered Revenue events",
                    perf.get("recovered_revenue", 0),
                ),
                MetricPoint(
                    "svc_recs20",
                    "Service Recommendations",
                    perf.get("service_recommendations", 0),
                ),
                MetricPoint(
                    "campaigns",
                    "Campaign suggestions",
                    (campaign.get("suggestions") if isinstance(campaign, dict) else 0) or 0,
                ),
            ],
        )
    )

    impact = perf.get("revenue_impact") or {}
    widgets.append(
        DashboardWidget(
            id="learning_loop",
            title="AI Learning Loop",
            kind="metrics",
            metrics=[
                MetricPoint(
                    "decision_accuracy",
                    "Decision Accuracy",
                    f"{perf.get('decision_accuracy', 0)*100:.0f}%",
                    tone="good",
                ),
                MetricPoint(
                    "appt_conversion",
                    "Appointment Conversion Improvement",
                    f"{perf.get('appointment_conversion_improvement', 0)*100:.0f}%",
                ),
                MetricPoint(
                    "repair_approval",
                    "Repair Approval Rate",
                    f"{perf.get('repair_approval_rate', 0)*100:.0f}%",
                ),
                MetricPoint(
                    "retention_improve",
                    "Customer Retention Improvement",
                    f"{perf.get('customer_retention_improvement', 0)*100:.0f}%",
                ),
                MetricPoint(
                    "revenue_impact",
                    "Revenue Impact success",
                    f"{(impact.get('success_rate') if isinstance(impact, dict) else 0) or 0:.0%}",
                ),
            ],
        )
    )

    return widgets


def build_daily_summary(sources: dict[str, Any], performance: dict[str, Any]) -> dict[str, Any]:
    executive = sources.get("executive") or {}
    live = executive.get("live") or {}
    return {
        "appointments_today": performance.get("appointments_today"),
        "ai_conversations": live.get("ai_conversations")
        or (sources.get("conversation") or {}).get("open_conversations"),
        "revenue_opportunities": performance.get("open_revenue_opportunities"),
        "todays_revenue": live.get("todays_revenue"),
        "missed_calls": live.get("missed_calls"),
        "human_escalations": live.get("human_escalations"),
        "workflow_success_rate": performance.get("workflow_success_rate"),
        "system_note": "Owner Dashboard is read-only",
    }
