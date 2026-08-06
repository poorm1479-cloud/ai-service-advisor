"""Shared SMS runtime singleton for webhook + inbox APIs."""

from __future__ import annotations

from app.sms.factory import SmsRuntime, build_sms_runtime

_runtime: SmsRuntime | None = None


def get_sms_runtime() -> SmsRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_sms_runtime()
    return _runtime


def peek_sms_runtime() -> SmsRuntime | None:
    """Return the singleton if already built — never cold-starts the AI stack."""
    return _runtime


def reset_sms_runtime() -> None:
    global _runtime
    _runtime = None
