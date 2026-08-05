"""Communication agent tests."""

from __future__ import annotations

import pytest

from app.agents.communication.models import RawInboundMessage
from app.agents.communication.service import CommunicationAgent


@pytest.mark.asyncio
async def test_normalize_sms(context):
    agent = CommunicationAgent()
    result = await agent.run(
        RawInboundMessage(channel="sms", content="  Need an oil change  ", sender_identifier="+15551212"),
        context,
    )
    assert result.success
    assert result.data is not None
    assert result.data.channel == "sms"
    assert result.data.body == "Need an oil change"
    assert result.data.direction == "incoming"
    assert context.channel == "sms"


@pytest.mark.asyncio
async def test_all_supported_channels(context):
    agent = CommunicationAgent()
    for channel in ("phone", "sms", "email", "facebook", "website_chat", "walk_in"):
        result = await agent.normalize(
            RawInboundMessage(channel=channel, content="Hello", subject="Hi"),
            context,
        )
        assert result.success, channel
        assert result.data.channel == channel


@pytest.mark.asyncio
async def test_reject_empty_and_unknown(context):
    agent = CommunicationAgent()
    empty = await agent.run(RawInboundMessage(channel="sms", content="   "), context)
    assert not empty.success

    bad = await agent.run(RawInboundMessage(channel="carrier-pigeon", content="hi"), context)
    assert not bad.success
