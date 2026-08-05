"""Retry helpers shared by all agents."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.agents.base.config import agent_settings
from app.agents.base.errors import AgentRetryExhaustedError

T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_attempts: int = agent_settings.retry_max_attempts
    base_delay_ms: int = agent_settings.retry_base_delay_ms
    max_delay_ms: int = agent_settings.retry_max_delay_ms
    jitter: bool = agent_settings.retry_jitter
    retry_on: tuple[type[BaseException], ...] = (Exception,)

    def delay_seconds(self, attempt: int) -> float:
        """Exponential backoff for attempt index starting at 1."""
        delay_ms = min(self.base_delay_ms * (2 ** (attempt - 1)), self.max_delay_ms)
        if self.jitter:
            delay_ms = delay_ms * (0.5 + random.random())
        return delay_ms / 1000.0


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    agent: str | None = None,
    correlation_id: str | None = None,
) -> T:
    """Execute an async operation with exponential backoff retries."""
    policy = policy or RetryPolicy()
    last_error: BaseException | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except policy.retry_on as exc:  # type: ignore[misc]
            last_error = exc
            if attempt >= policy.max_attempts:
                break
            await asyncio.sleep(policy.delay_seconds(attempt))

    raise AgentRetryExhaustedError(
        f"Operation failed after {policy.max_attempts} attempts",
        agent=agent,
        correlation_id=correlation_id,
        attempts=policy.max_attempts,
        cause=last_error,
    ) from last_error
