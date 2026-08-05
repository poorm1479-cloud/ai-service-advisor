"""Supervisor agent tests."""

from __future__ import annotations

import pytest

from app.agents.supervisor.models import AgentStageOutput, SupervisorReviewRequest
from app.agents.supervisor.service import SupervisorAgent


@pytest.mark.asyncio
async def test_ok_pipeline(context):
    agent = SupervisorAgent()
    result = await agent.review(
        SupervisorReviewRequest(
            stages=[
                AgentStageOutput(agent="communication", success=True, data={"ok": True}),
                AgentStageOutput(agent="intent", success=True, data={"intent": "other"}),
            ],
            intent="other",
        ),
        context,
    )
    assert result.success
    assert result.data.status == "ok"
    assert not result.data.escalate
    assert result.data.owner_summary


@pytest.mark.asyncio
async def test_escalate_on_emergency_and_errors(context):
    agent = SupervisorAgent()
    result = await agent.review(
        SupervisorReviewRequest(
            stages=[
                AgentStageOutput(agent="intent", success=True, data={"intent": "emergency"}),
                AgentStageOutput(agent="scheduling", success=False, error="boom", escalate=True),
            ],
            intent="emergency",
            is_emergency=True,
        ),
        context,
    )
    assert result.data.escalate
    assert result.data.status == "escalated"
    assert "Human takeover" in result.data.action_items[0]
    assert result.data.escalation_reason


@pytest.mark.asyncio
async def test_detect_cancel_vs_book_conflict(context):
    agent = SupervisorAgent()
    result = await agent.review(
        SupervisorReviewRequest(
            stages=[
                AgentStageOutput(
                    agent="intent",
                    success=True,
                    data={"intent": "cancel_appointment"},
                ),
                AgentStageOutput(
                    agent="scheduling",
                    success=True,
                    data={"action": "book", "success": True},
                ),
            ],
            intent="cancel_appointment",
        ),
        context,
    )
    assert result.data.conflicts
    assert result.data.escalate
