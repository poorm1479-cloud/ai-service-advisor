"""PluginContext — execution context passed to plugin.invoke."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class PluginContext:
    """Shared context for plugin capability invocations."""

    tenant_id: UUID | None = None
    shop_id: UUID | None = None
    user_id: UUID | None = None
    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None
    conversation_id: str | None = None
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    permissions: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_kwargs(self) -> dict[str, Any]:
        """Flatten context into kwargs for legacy invoke(**kwargs) handlers."""
        out: dict[str, Any] = {"_plugin_context": self}
        if self.shop_id is not None:
            out.setdefault("shop_id", self.shop_id)
        if self.customer_id is not None:
            out.setdefault("customer_id", self.customer_id)
        if self.vehicle_id is not None:
            out.setdefault("vehicle_id", self.vehicle_id)
        if self.correlation_id:
            out.setdefault("correlation_id", self.correlation_id)
        if self.conversation_id:
            out.setdefault("conversation_id", self.conversation_id)
        if self.trace_id:
            out.setdefault("trace_id", self.trace_id)
        return out

    @classmethod
    def from_agent_context(cls, agent_context: Any, **overrides: Any) -> PluginContext:
        """Build from AgentContext (or similar) without importing agents at module load."""
        shop_id = getattr(agent_context, "shop_id", None)
        conv_id = overrides.get(
            "conversation_id", getattr(agent_context, "conversation_id", None)
        )
        return cls(
            shop_id=overrides.get("shop_id", shop_id),
            customer_id=overrides.get("customer_id", getattr(agent_context, "customer_id", None)),
            vehicle_id=overrides.get("vehicle_id", getattr(agent_context, "vehicle_id", None)),
            correlation_id=overrides.get(
                "correlation_id", getattr(agent_context, "correlation_id", None)
            ),
            conversation_id=str(conv_id) if conv_id else None,
            tenant_id=overrides.get("tenant_id"),
            user_id=overrides.get("user_id"),
            workflow_id=overrides.get("workflow_id"),
            workflow_run_id=overrides.get("workflow_run_id"),
            permissions=list(overrides.get("permissions") or []),
            trace_id=str(overrides.get("trace_id") or getattr(agent_context, "correlation_id", None) or uuid4()),
            metadata=dict(overrides.get("metadata") or getattr(agent_context, "metadata", None) or {}),
        )

    @classmethod
    def for_shop(cls, shop_id: UUID, **kwargs: Any) -> PluginContext:
        return cls(shop_id=shop_id, **kwargs)
