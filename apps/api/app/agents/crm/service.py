"""CRM Agent — pure Decision Layer (summarize / recommend timeline writes)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.crm.interfaces import CrmStorePort
from app.agents.crm.models import CrmUpdateRequest, CrmUpdateResult, TimelineEntry
from app.agents.decisions.types import CrmUpdateDecision


class InMemoryCrmStore:
    def __init__(self) -> None:
        self._timeline: dict[tuple[UUID, UUID], list[TimelineEntry]] = defaultdict(list)

    async def add_communication(
        self,
        shop_id: UUID,
        customer_id: UUID,
        channel: str,
        message: str,
        direction: str = "incoming",
    ) -> TimelineEntry:
        entry = TimelineEntry(
            id=uuid4(),
            kind="communication",
            summary=f"{direction} {channel}: {message[:120]}",
            occurred_at=datetime.now(timezone.utc),
            metadata={"channel": channel, "direction": direction, "message": message},
        )
        self._timeline[(shop_id, customer_id)].append(entry)
        return entry

    async def add_repair_note(
        self, shop_id: UUID, customer_id: UUID, vehicle_id: UUID | None, note: str
    ) -> TimelineEntry:
        entry = TimelineEntry(
            id=uuid4(),
            kind="repair",
            summary=note[:200],
            occurred_at=datetime.now(timezone.utc),
            metadata={"vehicle_id": str(vehicle_id) if vehicle_id else None},
        )
        self._timeline[(shop_id, customer_id)].append(entry)
        return entry

    async def add_timeline(
        self, shop_id: UUID, customer_id: UUID, kind: str, summary: str
    ) -> TimelineEntry:
        entry = TimelineEntry(
            id=uuid4(),
            kind=kind,
            summary=summary,
            occurred_at=datetime.now(timezone.utc),
        )
        self._timeline[(shop_id, customer_id)].append(entry)
        return entry

    async def list_timeline(self, shop_id: UUID, customer_id: UUID) -> list[TimelineEntry]:
        return list(self._timeline.get((shop_id, customer_id), []))


class CrmAgent(Agent[CrmUpdateRequest, CrmUpdateResult]):
    """Decision-only CRM AI — recommends timeline updates; Workflow writes."""

    name = "crm"

    def __init__(self, store: CrmStorePort | None = None) -> None:
        super().__init__()
        self._store = store or InMemoryCrmStore()

    @property
    def store(self) -> CrmStorePort:
        return self._store

    async def handle(
        self, payload: CrmUpdateRequest, context: AgentContext
    ) -> AgentResult[CrmUpdateResult]:
        return await self.update(payload, context)

    async def update(
        self, request: CrmUpdateRequest, context: AgentContext
    ) -> AgentResult[CrmUpdateResult]:
        customer_id = request.customer_id or context.customer_id
        decision = CrmUpdateDecision(
            customer_id=customer_id,
            channel=request.channel,
            message=request.message,
            intent=request.intent,
            vehicle_id=request.vehicle_id or context.vehicle_id,
            repair_note=request.repair_note,
            rationale="Recommend CRM timeline update from conversation",
        )

        if customer_id is None:
            return AgentResult.ok(
                CrmUpdateResult(
                    customer_id=None,
                    customer_summary="No customer linked; CRM update skipped.",
                    decision=decision,
                )
            )

        # Read-only preview of existing timeline for summarization
        timeline = await self._store.list_timeline(context.shop_id, customer_id)
        summary = self.generate_customer_summary(customer_id, timeline, request.intent)

        return AgentResult.ok(
            CrmUpdateResult(
                customer_id=customer_id,
                communication_recorded=False,
                repair_updated=False,
                timeline_entries=timeline,
                customer_summary=summary,
                decision=decision,
            )
        )

    def generate_customer_summary(
        self,
        customer_id: UUID,
        timeline: list[TimelineEntry],
        intent: str | None,
    ) -> str:
        parts = [f"Customer {customer_id}: {len(timeline)} timeline events."]
        if intent:
            parts.append(f"Latest intent: {intent}.")
        if timeline:
            last = timeline[-1]
            parts.append(f"Last activity ({last.kind}): {last.summary}")
        return " ".join(parts)
