"""In-process async event bus (default Phase 5 transport)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from app.agents.base.config import agent_settings
from app.agents.base.errors import AgentValidationError
from app.agents.base.logging import get_agent_logger, log_extra
from app.agents.bus.protocol import EventHandler
from app.agents.events.envelope import EventEnvelope

_WILDCARD = "*"


class InMemoryEventBus:
    """Async in-memory event bus with fan-out and isolated handler errors."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._logger = get_agent_logger("event_bus")
        self._history: list[EventEnvelope[Any]] = []

    @property
    def history(self) -> list[EventEnvelope[Any]]:
        return list(self._history)

    async def publish(self, envelope: EventEnvelope[Any]) -> None:
        handlers = list(self._handlers.get(envelope.event_type, []))
        handlers.extend(self._handlers.get(_WILDCARD, []))
        self._history.append(envelope)

        self._logger.debug(
            "bus.publish %s",
            envelope.event_type,
            extra=log_extra(
                correlation_id=envelope.correlation_id,
                shop_id=str(envelope.shop_id),
                event_type=envelope.event_type,
            ),
        )

        if not handlers:
            return

        results = await asyncio.gather(
            *[self._safe_invoke(handler, envelope) for handler in handlers],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                self._logger.error(
                    "bus.handler_error %s",
                    result,
                    extra=log_extra(
                        correlation_id=envelope.correlation_id,
                        event_type=envelope.event_type,
                    ),
                )

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        existing = self._handlers[event_type]
        if len(existing) >= agent_settings.bus_max_handlers_per_event:
            raise AgentValidationError(
                f"Max handlers reached for event type '{event_type}'",
                agent="event_bus",
            )
        if handler not in existing:
            existing.append(handler)

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
        self._history.clear()

    async def _safe_invoke(self, handler: EventHandler, envelope: EventEnvelope[Any]) -> None:
        await handler(envelope)
