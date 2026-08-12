"""Paid plan upgrades require successful Stripe payment."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.exceptions import ValidationError
from app.saas import api as billing_api
from app.saas.billing import BillingService


@pytest.mark.asyncio
async def test_create_checkout_requires_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_id = uuid4()
    svc = BillingService()

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, model, plan_id):
            return SimpleNamespace(
                id=plan_id,
                is_public=True,
                price_cents_monthly=4900,
                stripe_price_id="price_test",
            )

        async def scalar(self, _stmt):
            return SimpleNamespace(
                id=uuid4(),
                shop_id=shop_id,
                plan_id="free",
                stripe_customer_id=None,
            )

        async def flush(self):
            return None

        def add(self, _obj):
            return None

        async def commit(self):
            return None

    monkeypatch.setattr("app.saas.billing.SessionLocal", lambda: _Session())
    monkeypatch.setattr("app.saas.billing.settings.stripe_secret_key", "")

    with pytest.raises(ValidationError, match="Paid plan upgrades require a successful checkout"):
        await svc.create_checkout(
            shop_id=shop_id,
            plan_id="pro",
            success_url="http://localhost/ok",
            cancel_url="http://localhost/cancel",
        )


@pytest.mark.asyncio
async def test_apply_paid_checkout_skips_unpaid_payment() -> None:
    calls: list[dict] = []

    class _Billing:
        async def apply_checkout_completed(self, **kwargs):
            calls.append(kwargs)

    applied = await billing_api._apply_paid_checkout(
        _Billing(),  # type: ignore[arg-type]
        {
            "payment_status": "unpaid",
            "metadata": {"shop_id": str(uuid4()), "plan_id": "pro"},
            "customer": "cus_x",
            "subscription": "sub_x",
        },
    )
    assert applied is False
    assert calls == []


@pytest.mark.asyncio
async def test_apply_paid_checkout_upgrades_when_paid() -> None:
    shop_id = uuid4()
    calls: list[dict] = []

    class _Billing:
        async def apply_checkout_completed(self, **kwargs):
            calls.append(kwargs)

    applied = await billing_api._apply_paid_checkout(
        _Billing(),  # type: ignore[arg-type]
        {
            "payment_status": "paid",
            "metadata": {"shop_id": str(shop_id), "plan_id": "pro"},
            "customer": "cus_x",
            "subscription": "sub_x",
        },
    )
    assert applied is True
    assert len(calls) == 1
    assert calls[0]["shop_id"] == shop_id
    assert calls[0]["plan_id"] == "pro"


@pytest.mark.asyncio
async def test_stripe_webhook_ignores_unpaid_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    calls: list[dict] = []

    class _Billing:
        async def apply_checkout_completed(self, **kwargs):
            calls.append(kwargs)

        async def apply_payment_failed(self, **kwargs):
            return True

    monkeypatch.setattr(billing_api, "BillingService", lambda: _Billing())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/billing/webhooks/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "payment_status": "unpaid",
                        "metadata": {"shop_id": str(uuid4()), "plan_id": "pro"},
                        "customer": "cus_x",
                        "subscription": "sub_x",
                    }
                },
            },
        )
    assert res.status_code == 200
    assert calls == []


@pytest.mark.asyncio
async def test_stripe_webhook_upgrades_on_paid_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app

    shop_id = uuid4()
    calls: list[dict] = []

    class _Billing:
        async def apply_checkout_completed(self, **kwargs):
            calls.append(kwargs)

        async def apply_payment_failed(self, **kwargs):
            return True

    monkeypatch.setattr(billing_api, "BillingService", lambda: _Billing())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/billing/webhooks/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "payment_status": "paid",
                        "metadata": {"shop_id": str(shop_id), "plan_id": "enterprise"},
                        "customer": "cus_y",
                        "subscription": "sub_y",
                    }
                },
            },
        )
    assert res.status_code == 200
    assert len(calls) == 1
    assert calls[0]["plan_id"] == "enterprise"
    assert calls[0]["shop_id"] == shop_id
