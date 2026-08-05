"""Retry helper tests."""

from __future__ import annotations

import pytest

from app.agents.base.errors import AgentRetryExhaustedError
from app.agents.base.retry import RetryPolicy, with_retry


@pytest.mark.asyncio
async def test_retry_succeeds_after_failures():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("fail")
        return "ok"

    result = await with_retry(
        flaky,
        policy=RetryPolicy(max_attempts=3, base_delay_ms=1, jitter=False),
    )
    assert result == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    async def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(AgentRetryExhaustedError) as exc:
        await with_retry(
            always_fail,
            policy=RetryPolicy(max_attempts=2, base_delay_ms=1, jitter=False),
            agent="test",
        )
    assert exc.value.attempts == 2
    assert exc.value.agent == "test"
