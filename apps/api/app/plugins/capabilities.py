"""Backward-compatible re-exports — prefer app.plugins.framework.capability."""

from __future__ import annotations

from app.plugins.framework.capability import (
    Capability,
    CapabilityBinding,
    CapabilityHandler,
    CapabilityRegistry,
    get_capability_registry,
    reset_capability_registry,
)

__all__ = [
    "Capability",
    "CapabilityBinding",
    "CapabilityHandler",
    "CapabilityRegistry",
    "get_capability_registry",
    "reset_capability_registry",
]
