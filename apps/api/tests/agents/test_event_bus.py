"""Event bus tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.bus.in_memory import InMemoryEventBus
from app.agents.events.envelope import EventEnvelope


@pytest.mark.asyncio
async def test_publish_invokes_subscribers():
    bus = InMemoryEventBus()
    seen: list[str] = []

    async def handler(envelope: EventEnvelope) -> None:
        seen.append(envelope.event_type)

    bus.subscribe("test.event", handler)
    await bus.publish(
        EventEnvelope(
            event_type="test.event",
            payload={"ok": True},
            shop_id=uuid4(),
            correlation_id="c1",
        )
    )
    assert seen == ["test.event"]
    assert len(bus.history) == 1


@pytest.mark.asyncio
async def test_wildcard_subscription():
    bus = InMemoryEventBus()
    seen: list[str] = []

    async def handler(envelope: EventEnvelope) -> None:
        seen.append(envelope.event_type)

    bus.subscribe("*", handler)
    await bus.publish(
        EventEnvelope(
            event_type="a",
            payload=None,
            shop_id=uuid4(),
            correlation_id="c",
        )
    )
    await bus.publish(
        EventEnvelope(
            event_type="b",
            payload=None,
            shop_id=uuid4(),
            correlation_id="c",
        )
    )
    assert seen == ["a", "b"]


@pytest.mark.asyncio
async def test_handler_error_does_not_break_publish():
    bus = InMemoryEventBus()
    ok: list[bool] = []

    async def bad(_envelope: EventEnvelope) -> None:
        raise RuntimeError("boom")

    async def good(_envelope: EventEnvelope) -> None:
        ok.append(True)

    bus.subscribe("x", bad)
    bus.subscribe("x", good)
    await bus.publish(
        EventEnvelope(event_type="x", payload=None, shop_id=uuid4(), correlation_id="c")
    )
    assert ok == [True]
