"""Workflow event bus — pub/sub with durable history via store."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from app.workflows.models import DomainEvent
from app.workflows.store import WorkflowStorePort

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class WorkflowEventBus:
    """In-process async bus used by the workflow engine.

    Compatible conceptually with the Phase 5 agent EventBus, but typed to
    DomainEvent so workflows stay independent of agent envelopes.

    Observers receive every published event (and emit_and_run notifications)
    without participating in workflow fan-out — used by Admin Notification Center.
    """

    def __init__(self, store: WorkflowStorePort | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._observers: list[EventHandler] = []
        self._store = store
        self._lock = asyncio.Lock()

    def set_store(self, store: WorkflowStorePort) -> None:
        self._store = store

    async def publish(self, event: DomainEvent) -> None:
        if self._store is not None:
            await self._store.append_event(event)
        handlers = list(self._handlers.get(event.event_type.value, []))
        handlers.extend(self._handlers.get("*", []))
        if handlers:
            results = await asyncio.gather(
                *[self._safe(h, event) for h in handlers],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    # Isolated — runner/handlers log their own failures
                    pass
        await self.notify_observers(event)

    async def notify_observers(self, event: DomainEvent) -> None:
        """Fan-out to side-effect observers without persisting or running workflows."""
        if not self._observers:
            return
        results = await asyncio.gather(
            *[self._safe(h, event) for h in list(self._observers)],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                pass

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def observe(self, handler: EventHandler) -> None:
        """Register a side-effect listener (admin notifications, metrics, etc.)."""
        if handler not in self._observers:
            self._observers.append(handler)

    def unobserve(self, handler: EventHandler) -> None:
        try:
            self._observers.remove(handler)
        except ValueError:
            return

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return

    def clear(self) -> None:
        self._handlers.clear()
        self._observers.clear()

    async def _safe(self, handler: EventHandler, event: DomainEvent) -> None:
        await handler(event)
