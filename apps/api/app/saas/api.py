"""Billing and usage API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, require_capabilities
from app.core.permissions.capabilities import StaffCapability
from app.domain.exceptions import NotFoundError, ValidationError
from app.infrastructure.config import settings
from app.saas.billing import BillingService
from app.saas.quotas import QuotaService
from app.saas.usage_tracking import UsageTrackingService

router = APIRouter(prefix="/v1/billing", tags=["billing"])

_require_billing = require_capabilities(StaffCapability.PAYMENT_HANDLING)


class CheckoutRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    success_url: str | None = None
    cancel_url: str | None = None


@router.get("/plans")
async def list_plans() -> dict:
    plans = await BillingService().list_plans()
    return {
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price_cents_monthly": p.price_cents_monthly,
                "ai_calls_monthly": p.ai_calls_monthly,
                "sms_monthly": p.sms_monthly,
                "seats": p.seats,
            }
            for p in plans
        ]
    }


@router.get("/subscription")
async def get_subscription(current: CurrentUser = Depends(_require_billing)) -> dict:
    sub = await BillingService().get_subscription(current.shop_id)
    usage = await QuotaService().get_usage(current.shop_id)
    return {
        "subscription": {
            "shop_id": str(sub.shop_id),
            "status": sub.status,
            "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "plan": {
                "id": sub.plan.id,
                "name": sub.plan.name,
                "description": sub.plan.description,
                "price_cents_monthly": sub.plan.price_cents_monthly,
                "ai_calls_monthly": sub.plan.ai_calls_monthly,
                "sms_monthly": sub.plan.sms_monthly,
                "seats": sub.plan.seats,
            },
        },
        "usage": usage,
    }


@router.get("/ai-usage")
async def get_ai_usage(current: CurrentUser = Depends(_require_billing)) -> dict:
    """Per-shop AI usage monitoring (requests, tokens, SMS, voice, estimated cost)."""
    return await UsageTrackingService().get_usage(current.shop_id)


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current: CurrentUser = Depends(_require_billing),
) -> dict:
    try:
        return await BillingService().create_checkout(
            shop_id=current.shop_id,
            plan_id=body.plan_id,
            success_url=body.success_url or settings.billing_success_url,
            cancel_url=body.cancel_url or settings.billing_cancel_url,
            customer_email=current.email,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/portal")
async def create_portal(current: CurrentUser = Depends(_require_billing)) -> dict:
    try:
        return await BillingService().create_portal_session(shop_id=current.shop_id)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


_SUCCESSFUL_CHECKOUT_PAYMENT_STATUSES = frozenset({"paid", "no_payment_required"})


def _checkout_payment_succeeded(session: dict) -> bool:
    """True only when Stripe reports the checkout session payment as successful."""
    return str(session.get("payment_status") or "").lower() in _SUCCESSFUL_CHECKOUT_PAYMENT_STATUSES


async def _apply_paid_checkout(billing: BillingService, data: dict) -> bool:
    """Upgrade plan only after a successful Stripe checkout payment. Returns whether applied."""
    if not _checkout_payment_succeeded(data):
        return False
    meta = data.get("metadata") or {}
    shop_id = meta.get("shop_id") or data.get("client_reference_id")
    plan_id = meta.get("plan_id")
    if not shop_id or not plan_id:
        return False
    await billing.apply_checkout_completed(
        shop_id=UUID(str(shop_id)),
        plan_id=str(plan_id),
        stripe_customer_id=data.get("customer") if isinstance(data.get("customer"), str) else None,
        stripe_subscription_id=(
            data.get("subscription") if isinstance(data.get("subscription"), str) else None
        ),
    )
    return True


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    """Stripe webhook: upgrade only on successful payment; mark delinquent on failures."""
    payload = await request.json()
    event_type = payload.get("type")
    data = (payload.get("data") or {}).get("object") or {}
    billing = BillingService()
    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        # checkout.session.completed can fire with unpaid async methods — skip those.
        await _apply_paid_checkout(billing, data)
    elif event_type == "checkout.session.async_payment_failed":
        meta = data.get("metadata") or {}
        shop_raw = meta.get("shop_id") or data.get("client_reference_id")
        stripe_sub = data.get("subscription")
        await billing.apply_payment_failed(
            shop_id=UUID(str(shop_raw)) if shop_raw else None,
            stripe_subscription_id=stripe_sub if isinstance(stripe_sub, str) else None,
            status="incomplete",
        )
    elif event_type in {"invoice.payment_failed", "customer.subscription.updated"}:
        meta = data.get("metadata") or {}
        shop_raw = meta.get("shop_id")
        sub_status = data.get("status")
        # invoice.payment_failed → past_due; subscription.updated only when delinquent
        if event_type == "invoice.payment_failed" or sub_status in {
            "past_due",
            "unpaid",
            "incomplete",
            "incomplete_expired",
        }:
            stripe_sub = data.get("subscription") or data.get("id")
            await billing.apply_payment_failed(
                shop_id=UUID(shop_raw) if shop_raw else None,
                stripe_subscription_id=stripe_sub if isinstance(stripe_sub, str) else None,
                status=sub_status if isinstance(sub_status, str) else "past_due",
            )
    return {"received": True}
