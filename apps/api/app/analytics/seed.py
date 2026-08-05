"""Seed realistic daily metric facts for analytics demos / cold shops."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.analytics.models import ShopMetricFact
from app.analytics.store import AnalyticsStorePort


def seed_shop_facts(
    store: AnalyticsStorePort,
    shop_id: UUID,
    *,
    days: int = 90,
    end: date | None = None,
) -> list[ShopMetricFact]:
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    written: list[ShopMetricFact] = []
    for i in range(days):
        day = start + timedelta(days=i)
        weekday = day.weekday()  # 0=Mon
        weekend_factor = 0.55 if weekday >= 5 else 1.0
        wave = 1.0 + 0.08 * ((i % 14) / 14.0)
        revenue = Decimal(str(round(4200 * weekend_factor * wave + (i % 7) * 85, 2)))
        ros = max(1, int(12 * weekend_factor + (i % 5)))
        offered = max(ros, int(18 * weekend_factor + (i % 4)))
        booked = max(1, min(offered, int(offered * (0.62 + (i % 9) * 0.02))))
        active = 40 + (i % 20)
        returning = int(active * (0.58 + (i % 10) * 0.01))
        m_spend = Decimal(str(round(180 + (i % 6) * 25, 2)))
        m_rev = Decimal(str(round(float(m_spend) * (3.2 + (i % 5) * 0.15), 2)))
        mech_h = 48.0 * weekend_factor
        billed = mech_h * (0.72 + (i % 8) * 0.02)
        ai_conv = 20 + (i % 15)
        ai_ok = int(ai_conv * (0.78 + (i % 7) * 0.02))
        clv = Decimal(str(round(1850 + (i % 12) * 40, 2)))
        fact = ShopMetricFact(
            shop_id=shop_id,
            day=day,
            revenue=revenue,
            repair_orders=ros,
            customers_active=active,
            customers_returning=returning,
            appointments_offered=offered,
            appointments_booked=booked,
            marketing_spend=m_spend,
            marketing_revenue=m_rev,
            mechanic_hours=mech_h,
            billed_hours=round(billed, 2),
            ai_conversations=ai_conv,
            ai_resolved=ai_ok,
            clv_cohort_avg=clv,
        )
        store.save_fact(fact)
        written.append(fact)
    return written
