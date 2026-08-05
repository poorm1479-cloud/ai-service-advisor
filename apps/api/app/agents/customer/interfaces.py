"""Customer agent ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.agents.base.agent import AgentContext, AgentResult
from app.agents.customer.models import (
    CustomerProfile,
    CustomerResolveRequest,
    CustomerResolveResult,
)


class CustomerDirectoryPort(Protocol):
    """Persistence port — implement with CRM UoW or in-memory for tests."""

    async def find_by_id(self, shop_id: UUID, customer_id: UUID) -> CustomerProfile | None: ...

    async def find_by_phone(self, shop_id: UUID, phone: str) -> list[CustomerProfile]: ...

    async def find_by_email(self, shop_id: UUID, email: str) -> list[CustomerProfile]: ...

    async def search(self, shop_id: UUID, query: str) -> list[CustomerProfile]: ...

    async def create(self, profile: CustomerProfile) -> CustomerProfile: ...

    async def update(self, profile: CustomerProfile) -> CustomerProfile: ...

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> CustomerProfile: ...


class CustomerAgentPort(Protocol):
    async def resolve(
        self, request: CustomerResolveRequest, context: AgentContext
    ) -> AgentResult[CustomerResolveResult]: ...
