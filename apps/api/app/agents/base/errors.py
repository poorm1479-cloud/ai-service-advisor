"""Agent-specific exception hierarchy."""

from __future__ import annotations

from app.domain.exceptions import DomainError


class AgentError(DomainError):
    """Base error raised by agents."""

    def __init__(self, message: str, *, agent: str | None = None, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.agent = agent
        self.correlation_id = correlation_id


class AgentValidationError(AgentError):
    """Invalid input or payload for an agent."""


class AgentConflictError(AgentError):
    """Conflicting agent outputs or domain state."""


class AgentTimeoutError(AgentError):
    """Agent operation exceeded its time budget."""


class AgentRetryExhaustedError(AgentError):
    """Retry policy exhausted without success."""

    def __init__(
        self,
        message: str,
        *,
        agent: str | None = None,
        correlation_id: str | None = None,
        attempts: int = 0,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, agent=agent, correlation_id=correlation_id)
        self.attempts = attempts
        self.cause = cause
