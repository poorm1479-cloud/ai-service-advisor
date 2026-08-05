"""External Integration Layer — adapters only (does not replace CRM / Workflow / Plugins)."""

from __future__ import annotations

__all__ = [
    "get_integrations_runtime",
    "reset_integrations_runtime",
]


def __getattr__(name: str):
    if name in __all__:
        from app.integrations import factory as _factory

        return getattr(_factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
