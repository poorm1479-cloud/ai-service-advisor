"""Core agent protocol and result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from app.agents.base.errors import AgentError
from app.agents.base.logging import get_agent_logger, log_extra
from app.agents.base.retry import RetryPolicy, with_retry

InT = TypeVar("InT")
OutT = TypeVar("OutT")


@dataclass(slots=True)
class AgentContext:
    """Shared execution context passed through the agent pipeline."""

    shop_id: UUID
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    channel: str | None = None
    conversation_id: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class AgentResult(Generic[OutT]):
    success: bool
    data: OutT | None = None
    error: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        data: OutT,
        *,
        escalate: bool = False,
        escalation_reason: str | None = None,
        **metadata: Any,
    ) -> AgentResult[OutT]:
        return cls(
            success=True,
            data=data,
            escalate=escalate,
            escalation_reason=escalation_reason,
            metadata=metadata,
        )

    @classmethod
    def fail(
        cls,
        error: str,
        *,
        escalate: bool = False,
        escalation_reason: str | None = None,
        **metadata: Any,
    ) -> AgentResult[OutT]:
        return cls(
            success=False,
            error=error,
            escalate=escalate,
            escalation_reason=escalation_reason,
            metadata=metadata,
        )


class Agent(ABC, Generic[InT, OutT]):
    """Base class for specialized agents.

    Subclasses implement ``handle`` and optionally register event subscriptions.
    """

    name: str = "agent"
    retry_policy: RetryPolicy = RetryPolicy()

    def __init__(self) -> None:
        self._logger = get_agent_logger(self.name)

    @abstractmethod
    async def handle(self, payload: InT, context: AgentContext) -> AgentResult[OutT]:
        """Process one unit of work for this agent."""

    async def run(self, payload: InT, context: AgentContext) -> AgentResult[OutT]:
        """Execute with logging, retry, and normalized error handling."""
        # Subclasses that override __init__ without super() still get a logger.
        logger = getattr(self, "_logger", None) or get_agent_logger(self.name)
        self._logger = logger
        logger.info(
            "agent.start",
            extra=log_extra(
                correlation_id=context.correlation_id,
                shop_id=str(context.shop_id),
                agent=self.name,
            ),
        )

        async def _op() -> AgentResult[OutT]:
            return await self.handle(payload, context)

        try:
            result = await with_retry(
                _op,
                policy=self.retry_policy,
                agent=self.name,
                correlation_id=context.correlation_id,
            )
        except AgentError as exc:
            logger.error(
                "agent.error %s",
                str(exc),
                extra=log_extra(
                    correlation_id=context.correlation_id,
                    shop_id=str(context.shop_id),
                    agent=self.name,
                ),
            )
            return AgentResult.fail(str(exc), escalate=True, escalation_reason=str(exc))
        except Exception as exc:  # noqa: BLE001 — boundary catch for pipeline safety
            logger.exception(
                "agent.unexpected",
                extra=log_extra(
                    correlation_id=context.correlation_id,
                    shop_id=str(context.shop_id),
                    agent=self.name,
                ),
            )
            return AgentResult.fail(
                f"Unexpected error in {self.name}: {exc}",
                escalate=True,
                escalation_reason=str(exc),
            )

        level = "info" if result.success else "warning"
        getattr(logger, level)(
            "agent.done success=%s escalate=%s",
            result.success,
            result.escalate,
            extra=log_extra(
                correlation_id=context.correlation_id,
                shop_id=str(context.shop_id),
                agent=self.name,
            ),
        )
        return result
