"""Modular AI Agent Framework — Phase 5.

Specialized agents communicate via an internal event bus.
MCP tool adapters provide future Model Context Protocol compatibility.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AgentOrchestrator",
    "AgentRuntime",
    "build_agent_runtime",
]


def __getattr__(name: str) -> Any:
    if name == "AgentOrchestrator":
        from app.agents.orchestrator import AgentOrchestrator

        return AgentOrchestrator
    if name in {"AgentRuntime", "build_agent_runtime"}:
        from app.agents import factory as _factory

        return getattr(_factory, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
