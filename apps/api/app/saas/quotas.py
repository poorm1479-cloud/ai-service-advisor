"""Per-shop usage metering and plan quotas."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.exceptions import ValidationError
from app.infrastructure.database import Base, SessionLocal
from app.saas.billing import BillingService


class ShopUsageCounterModel(Base):
    __tablename__ = "shop_usage_counters"
    __table_args__ = (
        UniqueConstraint("shop_id", "period_ym", "metric", name="uq_shop_usage_period_metric"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"))
    period_ym: Mapped[str] = mapped_column(String(7), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def _period_ym(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


class QuotaService:
    def __init__(self) -> None:
        self._billing = BillingService()

    async def get_usage(self, shop_id: UUID) -> dict:
        period = _period_ym()
        sub = await self._billing.get_subscription(shop_id)
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(ShopUsageCounterModel).where(
                        ShopUsageCounterModel.shop_id == shop_id,
                        ShopUsageCounterModel.period_ym == period,
                    )
                )
            ).all()
            counts = {r.metric: r.count for r in rows}
        return {
            "period": period,
            "plan_id": sub.plan.id,
            "limits": {
                "ai_calls": sub.plan.ai_calls_monthly,
                "sms": sub.plan.sms_monthly,
                "seats": sub.plan.seats,
            },
            "usage": {
                "ai_calls": counts.get("ai_calls", 0),
                "sms": counts.get("sms", 0),
            },
        }

    async def consume(self, shop_id: UUID, metric: str, amount: int = 1) -> None:
        if amount <= 0:
            return
        period = _period_ym()
        sub = await self._billing.get_subscription(shop_id)
        limit = sub.plan.ai_calls_monthly if metric == "ai_calls" else sub.plan.sms_monthly
        async with SessionLocal() as session:
            row = await session.scalar(
                select(ShopUsageCounterModel).where(
                    ShopUsageCounterModel.shop_id == shop_id,
                    ShopUsageCounterModel.period_ym == period,
                    ShopUsageCounterModel.metric == metric,
                )
            )
            if row is None:
                row = ShopUsageCounterModel(
                    id=uuid4(),
                    shop_id=shop_id,
                    period_ym=period,
                    metric=metric,
                    count=0,
                )
                session.add(row)
                await session.flush()
            current = int(row.count)
            if current + amount > limit:
                await session.rollback()
                raise ValidationError(
                    f"{metric} monthly quota exceeded ({current}/{limit}). Upgrade your plan."
                )
            previous = current
            row.count = current + amount
            new_count = current + amount
            await session.commit()

        # Soft warning at 80% of plan limit (ai_calls / sms). Dedupe via notification key.
        if limit > 0 and metric in {"ai_calls", "sms"}:
            threshold = max(1, int(limit * 0.8))
            if previous < threshold <= new_count:
                try:
                    from app.workflows.emitter import emit_domain_event
                    from app.workflows.enums import DomainEventType

                    percent = int(round((new_count / limit) * 100))
                    await emit_domain_event(
                        shop_id=shop_id,
                        event_type=DomainEventType.BILLING_QUOTA_WARNING,
                        payload={
                            "metric": metric,
                            "usage": new_count,
                            "limit": limit,
                            "percent": percent,
                            "period": period,
                        },
                        source="quotas",
                    )
                except Exception:
                    pass
