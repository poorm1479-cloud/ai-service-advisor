"""SaaS billing plans, subscriptions, and Stripe Checkout."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

import httpx
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.exceptions import NotFoundError, ValidationError
from app.infrastructure.config import settings
from app.infrastructure.database import Base, SessionLocal

logger = logging.getLogger("asa.billing")

# Subscription statuses treated as failed / delinquent payments for admin views.
FAILED_PAYMENT_STATUSES = frozenset({"past_due", "unpaid", "incomplete", "incomplete_expired"})

# Canonical plan quotas (UI + enforcement). Keeps existing DBs in sync without waiting on ops.
FREE_PLAN_QUOTAS = {
    "ai_calls_monthly": 10,
    "sms_monthly": 50,
    "seats": 2,
}
PRO_PLAN_QUOTAS = {
    "ai_calls_monthly": 150,
    "sms_monthly": 200,
    "seats": 4,
    "price_cents_monthly": 15000,
}
ENTERPRISE_PLAN_QUOTAS = {
    "ai_calls_monthly": 500,
    "sms_monthly": 500,
    "seats": 10,
    "price_cents_monthly": 40000,
}


class SaasPlanModel(Base):
    __tablename__ = "saas_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price_cents_monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_price_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ai_calls_monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    sms_monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ShopSubscriptionModel(Base):
    __tablename__ = "shop_subscriptions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), unique=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey("saas_plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="trialing")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(slots=True)
class PlanInfo:
    id: str
    name: str
    description: str
    price_cents_monthly: int
    ai_calls_monthly: int
    sms_monthly: int
    seats: int


@dataclass(slots=True)
class SubscriptionInfo:
    shop_id: UUID
    plan: PlanInfo
    status: str
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    stripe_customer_id: str | None


def _plan(m: SaasPlanModel) -> PlanInfo:
    return PlanInfo(
        id=m.id,
        name=m.name,
        description=m.description,
        price_cents_monthly=m.price_cents_monthly,
        ai_calls_monthly=m.ai_calls_monthly,
        sms_monthly=m.sms_monthly,
        seats=m.seats,
    )


async def _sync_plan_quotas(session, plan_id: str, quotas: dict[str, int]) -> None:
    """Ensure a plan row matches the given quotas (idempotent)."""
    plan = await session.get(SaasPlanModel, plan_id)
    if plan is None:
        return
    dirty = False
    for field, value in quotas.items():
        if getattr(plan, field) != value:
            setattr(plan, field, value)
            dirty = True
    if dirty:
        await session.commit()
        logger.info(
            "synced %s plan quotas: AI=%s SMS=%s seats=%s",
            plan_id,
            quotas["ai_calls_monthly"],
            quotas["sms_monthly"],
            quotas["seats"],
        )


async def _sync_canonical_plan_quotas(session) -> None:
    await _sync_plan_quotas(session, "free", FREE_PLAN_QUOTAS)
    await _sync_plan_quotas(session, "pro", PRO_PLAN_QUOTAS)
    await _sync_plan_quotas(session, "enterprise", ENTERPRISE_PLAN_QUOTAS)


class BillingServicePort(Protocol):
    """Abstraction for SaaS billing operations (customer + admin)."""

    async def list_plans(self) -> list[PlanInfo]: ...

    async def ensure_subscription(self, shop_id: UUID, plan_id: str = "free") -> SubscriptionInfo: ...

    async def get_subscription(self, shop_id: UUID) -> SubscriptionInfo: ...

    async def create_checkout(
        self,
        *,
        shop_id: UUID,
        plan_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict: ...

    async def apply_checkout_completed(
        self,
        *,
        shop_id: UUID,
        plan_id: str,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> None: ...

    async def admin_set_plan(self, shop_id: UUID, plan_id: str) -> dict: ...

    async def apply_payment_failed(
        self,
        *,
        shop_id: UUID | None = None,
        stripe_subscription_id: str | None = None,
        status: str = "past_due",
    ) -> bool: ...

    async def create_portal_session(self, *, shop_id: UUID, return_url: str | None = None) -> dict: ...

    async def list_shops_summary(self) -> list[dict]: ...

    async def admin_monitor(self) -> dict: ...


class BillingService:
    async def list_plans(self) -> list[PlanInfo]:
        async with SessionLocal() as session:
            await _sync_canonical_plan_quotas(session)
            rows = (
                await session.scalars(
                    select(SaasPlanModel)
                    .where(SaasPlanModel.is_public.is_(True))
                    .order_by(SaasPlanModel.sort_order)
                )
            ).all()
            return [_plan(r) for r in rows]

    async def ensure_subscription(self, shop_id: UUID, plan_id: str = "free") -> SubscriptionInfo:
        async with SessionLocal() as session:
            await _sync_canonical_plan_quotas(session)
            existing = await session.scalar(
                select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
            )
            if existing:
                plan = await session.get(SaasPlanModel, existing.plan_id)
                assert plan
                return SubscriptionInfo(
                    shop_id=shop_id,
                    plan=_plan(plan),
                    status=existing.status,
                    trial_ends_at=existing.trial_ends_at,
                    current_period_end=existing.current_period_end,
                    cancel_at_period_end=existing.cancel_at_period_end,
                    stripe_customer_id=existing.stripe_customer_id,
                )
            now = datetime.now(timezone.utc)
            plan = await session.get(SaasPlanModel, plan_id)
            if plan is None:
                plan = await session.get(SaasPlanModel, "free")
            assert plan
            sub = ShopSubscriptionModel(
                id=uuid4(),
                shop_id=shop_id,
                plan_id=plan.id,
                status="trialing",
                trial_ends_at=now + timedelta(days=settings.billing_trial_days),
                created_at=now,
                updated_at=now,
            )
            session.add(sub)
            await session.commit()
            return SubscriptionInfo(
                shop_id=shop_id,
                plan=_plan(plan),
                status=sub.status,
                trial_ends_at=sub.trial_ends_at,
                current_period_end=sub.current_period_end,
                cancel_at_period_end=sub.cancel_at_period_end,
                stripe_customer_id=sub.stripe_customer_id,
            )

    async def get_subscription(self, shop_id: UUID) -> SubscriptionInfo:
        return await self.ensure_subscription(shop_id)

    async def create_checkout(
        self,
        *,
        shop_id: UUID,
        plan_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> dict:
        async with SessionLocal() as session:
            plan = await session.get(SaasPlanModel, plan_id)
            if plan is None or not plan.is_public:
                raise NotFoundError("Plan not found")
            if plan.price_cents_monthly <= 0:
                raise ValidationError("Free plan does not require checkout")

            sub = await session.scalar(
                select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
            )
            if sub is None:
                now = datetime.now(timezone.utc)
                sub = ShopSubscriptionModel(
                    id=uuid4(),
                    shop_id=shop_id,
                    plan_id="free",
                    status="trialing",
                    trial_ends_at=now + timedelta(days=settings.billing_trial_days),
                    created_at=now,
                    updated_at=now,
                )
                session.add(sub)
                await session.flush()

            if not settings.stripe_secret_key:
                # Never activate a paid plan without a successful Stripe payment.
                raise ValidationError(
                    "Paid plan upgrades require a successful checkout payment."
                )

            price_id = plan.stripe_price_id
            if not price_id:
                raise ValidationError("Plan is missing stripe_price_id")

            data = {
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "client_reference_id": str(shop_id),
                "metadata[shop_id]": str(shop_id),
                "metadata[plan_id]": plan.id,
            }
            if customer_email:
                data["customer_email"] = customer_email
            if sub.stripe_customer_id:
                data["customer"] = sub.stripe_customer_id

            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    "https://api.stripe.com/v1/checkout/sessions",
                    data=data,
                    auth=(settings.stripe_secret_key, ""),
                )
            if res.status_code >= 400:
                logger.error("stripe.checkout_failed status=%s body=%s", res.status_code, res.text)
                raise ValidationError("Unable to create checkout session")
            payload = res.json()
            await session.commit()
            return {
                "mode": "stripe",
                "checkout_url": payload["url"],
                "session_id": payload["id"],
                "plan_id": plan.id,
            }

    async def admin_set_plan(self, shop_id: UUID, plan_id: str) -> dict:
        """Platform-admin plan assignment (no Stripe checkout). Preserves subscription status."""
        async with SessionLocal() as session:
            plan = await session.get(SaasPlanModel, plan_id)
            if plan is None:
                raise NotFoundError("Plan not found")
            sub = await session.scalar(
                select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
            )
            now = datetime.now(timezone.utc)
            if sub is None:
                sub = ShopSubscriptionModel(
                    id=uuid4(),
                    shop_id=shop_id,
                    plan_id=plan.id,
                    status="active",
                    current_period_end=now + timedelta(days=30),
                    created_at=now,
                    updated_at=now,
                )
                session.add(sub)
            else:
                sub.plan_id = plan.id
                sub.updated_at = now
                if sub.current_period_end is None:
                    sub.current_period_end = now + timedelta(days=30)
            await session.commit()
            return {
                "ok": True,
                "shop_id": str(shop_id),
                "plan_id": plan.id,
                "plan_name": plan.name,
                "status": sub.status,
            }

    async def apply_checkout_completed(
        self,
        *,
        shop_id: UUID,
        plan_id: str,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> None:
        async with SessionLocal() as session:
            sub = await session.scalar(
                select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
            )
            now = datetime.now(timezone.utc)
            if sub is None:
                sub = ShopSubscriptionModel(
                    id=uuid4(),
                    shop_id=shop_id,
                    plan_id=plan_id,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
                session.add(sub)
            sub.plan_id = plan_id
            sub.status = "active"
            sub.stripe_customer_id = stripe_customer_id or sub.stripe_customer_id
            sub.stripe_subscription_id = stripe_subscription_id or sub.stripe_subscription_id
            sub.current_period_end = now + timedelta(days=30)
            sub.updated_at = now
            await session.commit()
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=shop_id,
                event_type=DomainEventType.BILLING_PAYMENT_SUCCEEDED,
                payload={
                    "plan_id": plan_id,
                    "stripe_customer_id": stripe_customer_id,
                    "stripe_subscription_id": stripe_subscription_id,
                },
                source="billing",
            )
        except Exception:
            pass

    async def apply_payment_failed(
        self,
        *,
        shop_id: UUID | None = None,
        stripe_subscription_id: str | None = None,
        status: str = "past_due",
    ) -> bool:
        """Mark a subscription as delinquent after a Stripe payment failure."""
        if status not in FAILED_PAYMENT_STATUSES:
            status = "past_due"
        async with SessionLocal() as session:
            sub: ShopSubscriptionModel | None = None
            if stripe_subscription_id:
                sub = await session.scalar(
                    select(ShopSubscriptionModel).where(
                        ShopSubscriptionModel.stripe_subscription_id == stripe_subscription_id
                    )
                )
            if sub is None and shop_id is not None:
                sub = await session.scalar(
                    select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
                )
            if sub is None:
                return False
            resolved_shop_id = sub.shop_id
            plan_id = sub.plan_id
            sub.status = status
            sub.updated_at = datetime.now(timezone.utc)
            await session.commit()
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=resolved_shop_id,
                event_type=DomainEventType.BILLING_PAYMENT_FAILED,
                payload={
                    "status": status,
                    "plan_id": plan_id,
                    "stripe_subscription_id": stripe_subscription_id,
                },
                source="billing",
            )
        except Exception:
            pass
        return True

    async def create_portal_session(self, *, shop_id: UUID, return_url: str | None = None) -> dict:
        async with SessionLocal() as session:
            sub = await session.scalar(
                select(ShopSubscriptionModel).where(ShopSubscriptionModel.shop_id == shop_id)
            )
            if sub is None or not sub.stripe_customer_id:
                raise ValidationError(
                    "No billing customer on file. Complete a paid checkout first."
                )
            if not settings.stripe_secret_key:
                return {
                    "mode": "dev",
                    "portal_url": return_url or settings.billing_portal_return_url,
                    "message": "Billing portal is unavailable; returning to billing page.",
                }
            data = {
                "customer": sub.stripe_customer_id,
                "return_url": return_url or settings.billing_portal_return_url,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    "https://api.stripe.com/v1/billing_portal/sessions",
                    data=data,
                    auth=(settings.stripe_secret_key, ""),
                )
            if res.status_code >= 400:
                logger.error("stripe.portal_failed status=%s body=%s", res.status_code, res.text)
                raise ValidationError("Unable to open billing portal")
            payload = res.json()
            return {"mode": "stripe", "portal_url": payload["url"]}

    async def list_shops_summary(self) -> list[dict]:
        async with SessionLocal() as session:
            from app.infrastructure.models import ShopModel

            rows = (
                await session.execute(
                    select(ShopModel, ShopSubscriptionModel, SaasPlanModel)
                    .outerjoin(ShopSubscriptionModel, ShopSubscriptionModel.shop_id == ShopModel.id)
                    .outerjoin(SaasPlanModel, SaasPlanModel.id == ShopSubscriptionModel.plan_id)
                    .order_by(ShopModel.created_at.desc())
                )
            ).all()
            out: list[dict] = []
            for shop, sub, plan in rows:
                sms_phone = shop.sms_phone_e164
                voice_phone = shop.voice_phone_e164
                out.append(
                    {
                        "shop_id": str(shop.id),
                        "shop_name": shop.name,
                        "shop_slug": shop.slug,
                        "plan_id": plan.id if plan else "free",
                        "plan_name": plan.name if plan else "Free",
                        "status": sub.status if sub else "none",
                        "created_at": shop.created_at.isoformat() if shop.created_at else None,
                        "sms_phone_e164": sms_phone,
                        "voice_phone_e164": voice_phone,
                        "twilio_phone_e164": sms_phone or voice_phone,
                    }
                )
            return out

    async def admin_monitor(self) -> dict:
        """Platform admin billing snapshot: subscriptions, plans, payments, revenue."""
        from app.infrastructure.models import ShopModel

        plans = await self.list_plans()
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopModel, ShopSubscriptionModel, SaasPlanModel)
                    .outerjoin(ShopSubscriptionModel, ShopSubscriptionModel.shop_id == ShopModel.id)
                    .outerjoin(SaasPlanModel, SaasPlanModel.id == ShopSubscriptionModel.plan_id)
                    .order_by(ShopModel.created_at.desc())
                )
            ).all()

        subscriptions: list[dict] = []
        failed_payments: list[dict] = []
        by_status: dict[str, int] = {}
        plan_active: dict[str, dict] = {}
        mrr_cents = 0
        paid_active = 0
        with_stripe = 0

        for shop, sub, plan in rows:
            status = sub.status if sub else "none"
            price = plan.price_cents_monthly if plan else 0
            by_status[status] = by_status.get(status, 0) + 1
            if sub and (sub.stripe_customer_id or sub.stripe_subscription_id):
                with_stripe += 1
            if status == "active" and price > 0:
                mrr_cents += price
                paid_active += 1
            if status == "active" and plan:
                bucket = plan_active.setdefault(
                    plan.id,
                    {
                        "id": plan.id,
                        "name": plan.name,
                        "price_cents_monthly": plan.price_cents_monthly,
                        "ai_calls_monthly": plan.ai_calls_monthly,
                        "sms_monthly": plan.sms_monthly,
                        "seats": plan.seats,
                        "active_subscribers": 0,
                        "mrr_cents": 0,
                    },
                )
                bucket["active_subscribers"] += 1
                if price > 0:
                    bucket["mrr_cents"] += price

            row = {
                "shop_id": str(shop.id),
                "shop_name": shop.name,
                "shop_slug": shop.slug,
                "plan_id": plan.id if plan else None,
                "plan_name": plan.name if plan else None,
                "status": status,
                "payment_status": status,
                "price_cents_monthly": price,
                "stripe_customer_id": sub.stripe_customer_id if sub else None,
                "stripe_subscription_id": sub.stripe_subscription_id if sub else None,
                "trial_ends_at": sub.trial_ends_at.isoformat() if sub and sub.trial_ends_at else None,
                "current_period_end": (
                    sub.current_period_end.isoformat() if sub and sub.current_period_end else None
                ),
                "cancel_at_period_end": bool(sub.cancel_at_period_end) if sub else False,
                "updated_at": sub.updated_at.isoformat() if sub and sub.updated_at else None,
            }
            subscriptions.append(row)
            if status in FAILED_PAYMENT_STATUSES:
                failed_payments.append(row)

        revenue_summary = {
            "subscriptions": len(subscriptions),
            "paid_active": paid_active,
            "trialing": by_status.get("trialing", 0),
            "active": by_status.get("active", 0),
            "failed_payments": len(failed_payments),
            "with_stripe": with_stripe,
            "mrr_cents": mrr_cents,
            "arr_cents": mrr_cents * 12,
        }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "subscriptions": revenue_summary["subscriptions"],
                "paid_active": revenue_summary["paid_active"],
                "mrr_cents": revenue_summary["mrr_cents"],
                "arr_cents": revenue_summary["arr_cents"],
                "failed_payments": revenue_summary["failed_payments"],
            },
            "revenue_summary": revenue_summary,
            "payment_status": {"by_status": by_status, "total": len(subscriptions)},
            "active_plans": sorted(
                plan_active.values(),
                key=lambda p: (-int(p["active_subscribers"]), str(p["name"])),
            ),
            "plans": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price_cents_monthly": p.price_cents_monthly,
                    "ai_calls_monthly": p.ai_calls_monthly,
                    "sms_monthly": p.sms_monthly,
                    "seats": p.seats,
                }
                for p in plans
            ],
            "subscriptions": subscriptions,
            "payments": subscriptions,
            "failed_payments": failed_payments,
        }
