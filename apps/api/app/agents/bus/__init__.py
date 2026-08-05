"""Internal event bus — Protocol + in-process implementation."""

from app.agents.bus.in_memory import InMemoryEventBus
from app.agents.bus.protocol import EventBus, EventHandler

__all__ = [
    "EventBus",
    "EventHandler",
    "InMemoryEventBus",
]
