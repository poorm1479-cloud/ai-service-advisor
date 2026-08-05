"""Customer Agent — pure Decision Layer (resolve / recommend create-merge).

Directory reads are allowed. Creates/merges/updates go through Workflow.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.errors import AgentValidationError
from app.agents.counselor.persona import is_placeholder_name, spoken_first_name
from app.agents.customer.interfaces import CustomerDirectoryPort
from app.agents.customer.models import (
    CustomerProfile,
    CustomerResolveRequest,
    CustomerResolveResult,
)
from app.agents.decisions.types import CustomerDecision

_PHONE_DIGITS = re.compile(r"\D+")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_DIGITS.sub("", phone)
    return digits or None


def _name_update_decision(
    existing: CustomerProfile, request: CustomerResolveRequest
) -> CustomerDecision | None:
    """If CRM has a placeholder name and the customer gave a real one, propose update."""
    new_name = (request.name or "").strip()
    if not new_name or not spoken_first_name(new_name):
        return None
    if not is_placeholder_name(existing.name):
        return None
    return CustomerDecision(
        action="update",
        primary_id=existing.id,
        name=new_name,
        phone=_normalize_phone(request.phone) or existing.phone,
        email=(request.email or existing.email),
        profile_patch={"name": new_name},
        rationale="Fill in real customer name before booking",
    )


class InMemoryCustomerDirectory:
    """Default directory for unit tests and standalone agent runs."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, CustomerProfile] = {}

    async def find_by_id(self, shop_id: UUID, customer_id: UUID) -> CustomerProfile | None:
        profile = self._by_id.get(customer_id)
        if profile and profile.shop_id == shop_id:
            return profile
        return None

    async def find_by_phone(self, shop_id: UUID, phone: str) -> list[CustomerProfile]:
        target = _normalize_phone(phone)
        return [
            p
            for p in self._by_id.values()
            if p.shop_id == shop_id and _normalize_phone(p.phone) == target
        ]

    async def find_by_email(self, shop_id: UUID, email: str) -> list[CustomerProfile]:
        target = email.lower().strip()
        return [
            p
            for p in self._by_id.values()
            if p.shop_id == shop_id and (p.email or "").lower() == target
        ]

    async def search(self, shop_id: UUID, query: str) -> list[CustomerProfile]:
        q = query.lower().strip()
        return [
            p
            for p in self._by_id.values()
            if p.shop_id == shop_id
            and (
                q in p.name.lower()
                or (p.phone and q in p.phone)
                or (p.email and q in p.email.lower())
            )
        ]

    async def create(self, profile: CustomerProfile) -> CustomerProfile:
        self._by_id[profile.id] = profile
        return profile

    async def update(self, profile: CustomerProfile) -> CustomerProfile:
        self._by_id[profile.id] = profile
        return profile

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> CustomerProfile:
        primary = await self.find_by_id(shop_id, primary_id)
        if primary is None:
            raise AgentValidationError("Primary customer not found", agent="customer")
        for dup_id in duplicate_ids:
            dup = await self.find_by_id(shop_id, dup_id)
            if dup is None:
                continue
            if not primary.phone and dup.phone:
                primary.phone = dup.phone
            if not primary.email and dup.email:
                primary.email = dup.email
            if not primary.address and dup.address:
                primary.address = dup.address
            del self._by_id[dup_id]
        self._by_id[primary.id] = primary
        return primary


class CustomerAgent(Agent[CustomerResolveRequest, CustomerResolveResult]):
    name = "customer"

    def __init__(self, directory: CustomerDirectoryPort | None = None) -> None:
        super().__init__()
        self._directory = directory or InMemoryCustomerDirectory()

    @property
    def directory(self) -> CustomerDirectoryPort:
        return self._directory

    async def handle(
        self, payload: CustomerResolveRequest, context: AgentContext
    ) -> AgentResult[CustomerResolveResult]:
        return await self.resolve(payload, context)

    async def resolve(
        self, request: CustomerResolveRequest, context: AgentContext
    ) -> AgentResult[CustomerResolveResult]:
        shop_id = context.shop_id

        if request.prefer_customer_id:
            existing = await self._directory.find_by_id(shop_id, request.prefer_customer_id)
            if existing:
                context.customer_id = existing.id
                update = _name_update_decision(existing, request)
                if update is not None:
                    provisional = CustomerProfile(
                        id=existing.id,
                        shop_id=existing.shop_id,
                        name=update.name or existing.name,
                        phone=existing.phone,
                        email=existing.email,
                        address=existing.address,
                        tags=list(existing.tags or []),
                    )
                    return AgentResult.ok(
                        CustomerResolveResult(
                            customer=provisional,
                            action="propose_update",
                            decision=update,
                        )
                    )
                return AgentResult.ok(
                    CustomerResolveResult(customer=existing, action="found_by_id")
                )

        candidates: list[CustomerProfile] = []
        if request.phone:
            candidates.extend(await self._directory.find_by_phone(shop_id, request.phone))
        if request.email:
            for c in await self._directory.find_by_email(shop_id, request.email):
                if c.id not in {x.id for x in candidates}:
                    candidates.append(c)
        if request.name and not candidates:
            candidates.extend(await self._directory.search(shop_id, request.name))

        if len(candidates) > 1:
            primary = candidates[0]
            duplicate_ids = [c.id for c in candidates[1:]]
            decision = CustomerDecision(
                action="merge",
                primary_id=primary.id,
                duplicate_ids=duplicate_ids,
                name=request.name,
                phone=_normalize_phone(request.phone),
                email=request.email,
                rationale="Multiple matches — recommend merge",
            )
            return AgentResult.ok(
                CustomerResolveResult(
                    customer=primary,
                    merged_from=duplicate_ids,
                    action="propose_merge",
                    decision=decision,
                )
            )

        if len(candidates) == 1:
            existing = candidates[0]
            context.customer_id = existing.id
            update = _name_update_decision(existing, request)
            if update is not None:
                provisional = CustomerProfile(
                    id=existing.id,
                    shop_id=existing.shop_id,
                    name=update.name or existing.name,
                    phone=existing.phone,
                    email=existing.email,
                    address=existing.address,
                    tags=list(existing.tags or []),
                )
                return AgentResult.ok(
                    CustomerResolveResult(
                        customer=provisional,
                        action="propose_update",
                        decision=update,
                    )
                )
            return AgentResult.ok(
                CustomerResolveResult(customer=existing, action="found")
            )

        if not request.create_if_missing:
            return AgentResult.ok(CustomerResolveResult(customer=None, action="not_found"))

        name = (request.name or "").strip()
        if not spoken_first_name(name):
            name = "Unknown Customer"
        decision = CustomerDecision(
            action="create",
            name=name,
            phone=_normalize_phone(request.phone),
            email=request.email.lower().strip() if request.email else None,
            rationale="No match — recommend create customer",
        )
        # Provisional profile for downstream AI (not persisted until Workflow applies)
        provisional = CustomerProfile(
            id=uuid4(),
            shop_id=shop_id,
            name=name,
            phone=decision.phone,
            email=decision.email,
        )
        return AgentResult.ok(
            CustomerResolveResult(
                customer=provisional,
                is_new=True,
                action="propose_create",
                decision=decision,
            )
        )

    async def update_profile(
        self, profile: CustomerProfile, context: AgentContext
    ) -> AgentResult[CustomerProfile]:
        """Propose profile update as a Decision — Workflow must apply."""
        decision = CustomerDecision(
            action="update",
            primary_id=profile.id,
            name=profile.name,
            phone=profile.phone,
            email=profile.email,
            profile_patch={
                "name": profile.name,
                "phone": profile.phone,
                "email": profile.email,
                "address": profile.address,
                "tags": list(profile.tags),
            },
            rationale="Recommend customer profile update",
        )
        # Attach decision on metadata via result — return profile unchanged pending apply
        result = AgentResult.ok(profile)
        result.metadata["decision"] = decision
        return result

    async def read_profile(
        self, customer_id: UUID, context: AgentContext
    ) -> AgentResult[CustomerProfile]:
        profile = await self._directory.find_by_id(context.shop_id, customer_id)
        if profile is None:
            return AgentResult.fail("Customer not found")
        return AgentResult.ok(profile)
