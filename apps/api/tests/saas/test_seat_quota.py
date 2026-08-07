"""Seat quota enforcement for plan limits."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.exceptions import ValidationError
from app.saas.quotas import QuotaService


@pytest.mark.asyncio
async def test_ensure_seat_available_blocks_when_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    svc = QuotaService()

    async def _sub(_shop_id):
        return SimpleNamespace(plan=SimpleNamespace(seats=2))

    async def _count(_shop_id):
        return 2

    monkeypatch.setattr(svc._billing, "get_subscription", _sub)
    monkeypatch.setattr(svc, "_seat_count", _count)

    with pytest.raises(ValidationError, match="seats quota exceeded"):
        await svc.ensure_seat_available(shop_id)


@pytest.mark.asyncio
async def test_ensure_seat_available_allows_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    svc = QuotaService()

    async def _sub(_shop_id):
        return SimpleNamespace(plan=SimpleNamespace(seats=2))

    async def _count(_shop_id):
        return 1

    monkeypatch.setattr(svc._billing, "get_subscription", _sub)
    monkeypatch.setattr(svc, "_seat_count", _count)

    await svc.ensure_seat_available(shop_id)


@pytest.mark.asyncio
async def test_get_usage_includes_seats(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    svc = QuotaService()

    async def _sub(_shop_id):
        return SimpleNamespace(
            plan=SimpleNamespace(
                id="free",
                ai_calls_monthly=50,
                sms_monthly=50,
                seats=2,
            )
        )

    async def _count(_shop_id):
        return 2

    class _SessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def scalars(self, *_a, **_k):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(svc._billing, "get_subscription", _sub)
    monkeypatch.setattr(svc, "_seat_count", _count)
    monkeypatch.setattr("app.saas.quotas.SessionLocal", lambda: _SessionCtx())

    usage = await svc.get_usage(shop_id)
    assert usage["limits"]["seats"] == 2
    assert usage["usage"]["seats"] == 2
