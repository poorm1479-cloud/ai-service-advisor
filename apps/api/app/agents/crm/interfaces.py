"""CRM agent ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.crm.models import CrmUpdateRequest, CrmUpdateResult, TimelineEntry


class CrmStorePort(Protocol):
    async def add_communication(
        self,
        shop_id: UUID,
        customer_id: UUID,
        channel: str,
        message: str,
        direction: str = "incoming",
    ) -> TimelineEntry: ...

    async def add_repair_note(
        self, shop_id: UUID, customer_id: UUID, vehicle_id: UUID | None, note: str
    ) -> TimelineEntry: ...

    async def add_timeline(
        self, shop_id: UUID, customer_id: UUID, kind: str, summary: str
    ) -> TimelineEntry: ...

    async def list_timeline(self, shop_id: UUID, customer_id: UUID) -> list[TimelineEntry]: ...


class CrmAgentPort(Protocol):
    async def update(
        self, request: CrmUpdateRequest, context: AgentContext
    ) -> AgentResult[CrmUpdateResult]: ...
