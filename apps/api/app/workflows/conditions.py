"""Condition evaluation against event payload + run context."""

from __future__ import annotations

from typing import Any

from app.workflows.models import WorkflowCondition
from app.workflows.enums import ConditionOperator


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_conditions(
    conditions: list[WorkflowCondition],
    *,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Return (matched, failure_reasons). Empty conditions always match."""
    if not conditions:
        return True, []

    merged = {**(context or {}), "payload": payload, **payload}
    failures: list[str] = []
    for cond in conditions:
        actual = _resolve_path(merged, cond.field) if "." in cond.field else merged.get(cond.field)
        ok = _compare(actual, cond.operator, cond.value)
        if not ok:
            failures.append(f"{cond.field} {cond.operator.value} {cond.value!r} (got {actual!r})")
    return (len(failures) == 0), failures


def _compare(actual: Any, op: ConditionOperator, expected: Any) -> bool:
    if op == ConditionOperator.EXISTS:
        return actual is not None
    if op == ConditionOperator.NOT_EXISTS:
        return actual is None
    if op == ConditionOperator.EQ:
        return actual == expected
    if op == ConditionOperator.NE:
        return actual != expected
    if op == ConditionOperator.GT:
        return actual is not None and actual > expected
    if op == ConditionOperator.GTE:
        return actual is not None and actual >= expected
    if op == ConditionOperator.LT:
        return actual is not None and actual < expected
    if op == ConditionOperator.LTE:
        return actual is not None and actual <= expected
    if op == ConditionOperator.IN:
        return actual in (expected or [])
    if op == ConditionOperator.CONTAINS:
        if actual is None:
            return False
        return expected in actual
    return False
