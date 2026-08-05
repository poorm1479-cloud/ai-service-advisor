"""Retry with exponential backoff for integration invokes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.mcp_hub.models import RetryPolicy
from app.mcp_hub.monitoring import McpHubMonitor

T = TypeVar("T")


class RetryableError(Exception):
    def __init__(self, message: str, *, kind: str = "unavailable") -> None:
        super().__init__(message)
        self.kind = kind


class RetryExecutor:
    def __init__(self, policy: RetryPolicy | None = None, monitor: McpHubMonitor | None = None) -> None:
        self.policy = policy or RetryPolicy()
        self._monitor = monitor

    def _is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, RetryableError):
            return exc.kind in self.policy.retryable_errors
        msg = str(exc).lower()
        return any(k in msg for k in self.policy.retryable_errors)

    async def run(self, fn: Callable[[], Awaitable[T]]) -> tuple[T, int]:
        attempts = 0
        delay = self.policy.base_delay_ms / 1000.0
        last_exc: BaseException | None = None
        while attempts < self.policy.max_attempts:
            attempts += 1
            try:
                result = await fn()
                return result, attempts
            except Exception as exc:
                last_exc = exc
                if attempts >= self.policy.max_attempts or not self._is_retryable(exc):
                    raise
                if self._monitor:
                    self._monitor.record_retry()
                await asyncio.sleep(min(delay, self.policy.max_delay_ms / 1000.0))
                delay *= self.policy.multiplier
        assert last_exc is not None
        raise last_exc
