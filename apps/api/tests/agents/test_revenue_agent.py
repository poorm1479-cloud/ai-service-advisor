"""Revenue agent tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.revenue.models import RevenueAnalysisRequest
from app.agents.revenue.service import RevenueAgent
from app.agents.vehicle.models import MaintenanceItem, VehicleRecord


@pytest.mark.asyncio
async def test_upsells_and_prediction(context):
    agent = RevenueAgent()
    result = await agent.analyze(
        RevenueAnalysisRequest(
            customer_id=uuid4(),
            vehicle=VehicleRecord(
                id=uuid4(),
                shop_id=context.shop_id,
                vin="1HGCM82633A004352",
                year=2018,
                make="Honda",
                model="Civic",
                mileage=45000,
            ),
            maintenance_timeline=[
                MaintenanceItem(
                    service="oil_change",
                    due_mileage=50000,
                    due_date=None,
                    status="due_soon",
                )
            ],
            declined_estimates=[{"service": "brakes", "amount": "320.00"}],
            days_since_last_visit=200,
            intent="price_question",
        ),
        context,
    )
    assert result.success
    assert result.data.lost_customer_risk > 0
    assert result.data.predicted_revenue > Decimal("0")
    assert any(u.service == "oil_change" for u in result.data.upsell_opportunities)
    assert any("declined" in u.reason.lower() for u in result.data.upsell_opportunities)
    assert result.data.notes
