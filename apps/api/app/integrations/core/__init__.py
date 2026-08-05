"""Integration core — adapter protocol, base class, and registry."""

from app.integrations.core.adapter import BaseAdapter
from app.integrations.core.interface import IntegrationAdapter
from app.integrations.core.registry import (
    AdapterRegistry,
    build_default_registry,
    get_adapter_registry,
    reset_adapter_registry,
)

__all__ = [
    "AdapterRegistry",
    "BaseAdapter",
    "IntegrationAdapter",
    "build_default_registry",
    "get_adapter_registry",
    "reset_adapter_registry",
]
