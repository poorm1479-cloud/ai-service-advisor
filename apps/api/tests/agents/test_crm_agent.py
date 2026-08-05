"""CRM agent tests — AI decides; Workflow executes."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentResult
from app.agents.crm.models import CrmUpdateRequest
from app.agents.crm.service import CrmAgent
from app.agents.decisions.bridge import apply_decisions, collect_decision, ports_from_agents


@pytest.mark.asyncio
async def test_update_communication_and_summary(context):
    agent = CrmAgent()
    customer_id = uuid4()
    context.customer_id = customer_id
    result = await agent.update(
        CrmUpdateRequest(
            customer_id=customer_id,
            channel="sms",
            message="Need brakes checked",
            intent="maintenance_question",
        ),
        context,
    )
    assert result.success
    assert result.data.decision is not None
    applied = await apply_decisions(
        shop_id=context.shop_id,
        decisions=[result.data.decision],
        ports=ports_from_agents(crm=agent),
        context=context,
    )
    assert applied.crm_result is not None
    assert applied.crm_result.communication_recorded
    assert applied.crm_result.timeline_entries
    assert "maintenance_question" in (applied.crm_result.customer_summary or "")


@pytest.mark.asyncio
async def test_skip_without_customer(context):
    agent = CrmAgent()
    result = await agent.update(CrmUpdateRequest(customer_id=None, message="hi", channel="sms"), context)
    assert result.success
    assert result.data.customer_id is None
    assert "skipped" in (result.data.customer_summary or "").lower()
