"""Industry benchmark definitions + comparison."""

from __future__ import annotations

from app.analytics.enums import KpiId
from app.analytics.models import BenchmarkRow, KpiMetric


# Industry averages for independent repair shops (illustrative production defaults)
INDUSTRY: dict[KpiId, dict[str, float]] = {
    KpiId.REVENUE: {"avg": 95000.0, "top": 140000.0, "unit": "usd_month"},
    KpiId.RETENTION: {"avg": 0.62, "top": 0.78, "unit": "ratio"},
    KpiId.AVERAGE_REPAIR_ORDER: {"avg": 385.0, "top": 520.0, "unit": "usd"},
    KpiId.CUSTOMER_LIFETIME_VALUE: {"avg": 2100.0, "top": 3400.0, "unit": "usd"},
    KpiId.APPOINTMENT_CONVERSION: {"avg": 0.58, "top": 0.75, "unit": "ratio"},
    KpiId.MARKETING_ROI: {"avg": 3.1, "top": 5.5, "unit": "x"},
    KpiId.MECHANIC_PRODUCTIVITY: {"avg": 0.75, "top": 0.88, "unit": "ratio"},
    KpiId.AI_SUCCESS_RATE: {"avg": 0.72, "top": 0.90, "unit": "ratio"},
}


def compare_benchmarks(kpis: list[KpiMetric]) -> list[BenchmarkRow]:
    rows: list[BenchmarkRow] = []
    by_id = {k.id: k for k in kpis}
    for kpi_id, meta in INDUSTRY.items():
        metric = by_id.get(kpi_id)
        if metric is None:
            continue
        shop = float(metric.value)
        avg = meta["avg"]
        top = meta["top"]
        # For monthly revenue KPI we compare period revenue scaled; value already period-based
        if shop >= top * 0.95:
            status = "ahead"
        elif shop >= avg * 0.92:
            status = "on_par"
        else:
            status = "behind"
        rows.append(
            BenchmarkRow(
                kpi=kpi_id,
                label=metric.label,
                shop_value=shop,
                industry_avg=avg,
                top_quartile=top,
                unit=meta["unit"],
                status=status,
            )
        )
    return rows


def apply_benchmark_fields(kpis: list[KpiMetric]) -> list[KpiMetric]:
    for k in kpis:
        meta = INDUSTRY.get(k.id)
        if not meta:
            continue
        k.benchmark = meta["avg"]
        if meta["avg"]:
            k.vs_benchmark_pct = round(((k.value - meta["avg"]) / meta["avg"]) * 100.0, 2)
        k.target = meta["top"]
    return kpis
