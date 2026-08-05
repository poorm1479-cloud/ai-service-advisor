"""Marketing agent tests — AI decides; Workflow dispatches."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents
from app.agents.marketing.models import MarketingActionType, MarketingRequest
from app.agents.marketing.service import LoggingMarketingDispatcher, MarketingAgent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        MarketingActionType.SMS_CAMPAIGN,
        MarketingActionType.EMAIL_CAMPAIGN,
        MarketingActionType.REVIEW_REQUEST,
        MarketingActionType.THANK_YOU,
        MarketingActionType.MAINTENANCE_REMINDER,
    ],
)
async def test_marketing_actions(context, action):
    dispatcher = LoggingMarketingDispatcher()
    agent = MarketingAgent(dispatcher)
    result = await agent.execute(
        MarketingRequest(
            action_type=action,
            customer_id=uuid4(),
            channel="sms" if "email" not in action.value else "email",
            context={
                "name": "Sam",
                "shop": "Main Street Auto",
                "service": "oil change",
                "due_mileage": 50000,
            },
        ),
        context,
    )
    assert result.success
    assert result.data.dispatched is False
    assert result.data.decision is not None
    assert result.data.body

    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[collect_decision(result)],
        ports=ports_from_agents(marketing=agent),
        context=context,
    )
    assert len(applied.marketing_results) == 1
    assert applied.marketing_results[0].dispatched
    assert len(dispatcher.sent) == 1
