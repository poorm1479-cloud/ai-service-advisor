"""AI usage monitoring — non-enforcing metering helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.saas.usage_tracking import (
    UsageTrackingService,
    get_usage_shop_id,
    record_ai_usage_if_scoped,
    usage_shop_scope,
    voice_duration_seconds,
)


def test_voice_duration_prefers_recording() -> None:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended = started + timedelta(seconds=120)
    assert (
        voice_duration_seconds(
            recording_duration_sec=45,
            started_at=started,
            ended_at=ended,
        )
        == 45
    )


def test_voice_duration_falls_back_to_timestamps() -> None:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended = started + timedelta(seconds=90)
    assert (
        voice_duration_seconds(
            recording_duration_sec=None,
            started_at=started,
            ended_at=ended,
        )
        == 90
    )


def test_usage_shop_scope_sets_and_resets() -> None:
    shop_id = uuid4()
    assert get_usage_shop_id() is None
    with usage_shop_scope(shop_id):
        assert get_usage_shop_id() == shop_id
    assert get_usage_shop_id() is None


@pytest.mark.asyncio
async def test_record_ai_usage_noop_without_shop() -> None:
    # Must not raise when no shop is scoped.
    await record_ai_usage_if_scoped(operation="extract", input_tokens=10, output_tokens=5)


@pytest.mark.asyncio
async def test_get_usage_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()

    class _FakeScalars:
        def all(self):
            return []

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def scalars(self, *_args, **_kwargs):
            return _FakeScalars()

    monkeypatch.setattr("app.saas.usage_tracking.SessionLocal", lambda: _FakeSession())
    usage = await UsageTrackingService().get_usage(shop_id)
    assert usage["shop_id"] == str(shop_id)
    assert usage["ai_requests"] == 0
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["sms_count"] == 0
    assert usage["voice_minutes"] == 0.0
    assert usage["estimated_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_record_ai_increments_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    captured: list[tuple] = []

    async def _fake_increment(self, sid, increments):
        captured.append((sid, increments))

    monkeypatch.setattr(UsageTrackingService, "_increment_many", _fake_increment)
    await UsageTrackingService().record_ai(
        shop_id, input_tokens=1000, output_tokens=500, requests=1
    )
    assert len(captured) == 1
    assert captured[0][0] == shop_id
    metrics = captured[0][1]
    assert metrics["ai_requests"] == 1
    assert metrics["input_tokens"] == 1000
    assert metrics["output_tokens"] == 500
    assert metrics["estimated_cost_micros"] > 0


@pytest.mark.asyncio
async def test_record_sms_and_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    captured: list[dict] = []

    async def _fake_increment(self, sid, increments):
        captured.append(increments)

    monkeypatch.setattr(UsageTrackingService, "_increment_many", _fake_increment)
    svc = UsageTrackingService()
    await svc.record_sms(shop_id, count=2)
    await svc.record_voice_seconds(shop_id, 120)
    assert captured[0]["sms_count"] == 2
    assert captured[1]["voice_seconds"] == 120
    assert captured[1]["estimated_cost_micros"] > 0
