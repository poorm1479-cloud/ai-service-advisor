"""Dashboard metrics helpers — read-only KPI calculations."""

from __future__ import annotations

from typing import Any


def rate(numerator: float | int, denominator: float | int) -> float:
    d = float(denominator)
    if d <= 0:
        return 0.0
    return round(float(numerator) / d, 4)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def performance_from_sources(sources: dict[str, Any]) -> dict[str, Any]:
    voice = sources.get("voice") or {}
    workflow = sources.get("workflow") or {}
    revenue = sources.get("revenue") or {}
    scheduling = sources.get("scheduling") or {}

    calls = safe_int(voice.get("call_volume") or voice.get("calls_started"))
    completed = safe_int(voice.get("calls_completed"))
    ai_res = safe_float(voice.get("ai_resolution_rate"))
    transfer = safe_float(voice.get("human_transfer_rate"))
    runs = safe_int(workflow.get("run_count"))
    succeeded = safe_int(workflow.get("succeeded"))
    failed = safe_int(workflow.get("failed"))

    return {
        "call_volume": calls,
        "ai_resolution_rate": ai_res,
        "human_transfer_rate": transfer,
        "workflow_success_rate": rate(succeeded, runs),
        "workflow_failure_rate": rate(failed, runs),
        "appointments_today": safe_int(scheduling.get("appointments_today")),
        "open_revenue_opportunities": safe_int(
            revenue.get("open_opportunities") or revenue.get("opportunity_count")
        ),
        "average_response_time_ms": safe_float(voice.get("average_response_time_ms")),
        "customer_satisfaction": voice.get("customer_satisfaction"),
        # Phase 20 — Revenue Intelligence & Retention KPIs
        "customer_retention_rate": safe_float(revenue.get("customer_retention_rate")),
        "lost_customer_risk": safe_int(revenue.get("lost_customer_risk")),
        "revenue_opportunities": safe_int(
            revenue.get("revenue_opportunities")
            or revenue.get("open_opportunities")
            or revenue.get("opportunity_count")
        ),
        "recovered_revenue": safe_int(revenue.get("recovered_revenue")),
        "service_recommendations": safe_int(revenue.get("service_recommendations")),
        "campaign_performance": revenue.get("campaign_performance")
        or {"suggestions": 0, "sent": 0, "auto_send_blocked": True},
        # Phase 21 — AI Learning Loop KPIs
        "decision_accuracy": safe_float(revenue.get("decision_accuracy")),
        "appointment_conversion_improvement": safe_float(
            revenue.get("appointment_conversion_improvement")
        ),
        "repair_approval_rate": safe_float(revenue.get("repair_approval_rate")),
        "customer_retention_improvement": safe_float(
            revenue.get("customer_retention_improvement")
        ),
        "revenue_impact": revenue.get("revenue_impact")
        or {"success_rate": 0.0, "samples": 0, "avg_score": 0.0},
    }


def system_health_from_sources(sources: dict[str, Any]) -> dict[str, Any]:
    plugins = sources.get("plugins") or {}
    healthy = 0
    total = 0
    details: list[dict[str, Any]] = []
    for plugin_id, status in plugins.items():
        total += 1
        st = (status or {}).get("status") if isinstance(status, dict) else None
        ok = st in {"healthy", "ok", "enabled"} or (isinstance(status, dict) and status.get("ok"))
        if ok:
            healthy += 1
        details.append({"plugin_id": plugin_id, "status": st or "unknown", "ok": bool(ok)})
    return {
        "status": "healthy" if total == 0 or healthy == total else ("degraded" if healthy else "down"),
        "plugins_healthy": healthy,
        "plugins_total": total,
        "details": details,
        "workflow_engine": (sources.get("workflow") or {}).get("engine_status", "unknown"),
    }
