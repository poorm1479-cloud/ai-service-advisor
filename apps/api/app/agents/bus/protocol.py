"""Event bus port — swap in-process for Redis/NATS later without changing agents."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from app.agents.events.envelope import EventEnvelope

T = TypeVar("T")

EventHandler = Callable[[EventEnvelope[Any]], Awaitable[None]]


class EventBus(Protocol):
    """Internal pub/sub bus used by all agents."""

    async def publish(self, envelope: EventEnvelope[Any]) -> None:
        """Publish an event to all subscribed handlers."""

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type (or '*' for all)."""

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""

    def clear(self) -> None:
        """Remove all subscriptions (tests / shutdown)."""
