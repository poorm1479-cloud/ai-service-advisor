"""Customer plugin service — wraps existing CustomerDirectoryPort (no rewrite)."""

from __future__ import annotations

from uuid import UUID

from app.agents.customer.interfaces import CustomerDirectoryPort
from app.agents.customer.models import CustomerProfile
from app.agents.customer.service import InMemoryCustomerDirectory


class CustomerPluginService:
    """Thin wrapper around existing customer directory implementation."""

    def __init__(self, directory: CustomerDirectoryPort | None = None) -> None:
        self._directory = directory or InMemoryCustomerDirectory()

    @property
    def directory(self) -> CustomerDirectoryPort:
        """Expose underlying port for agent DI compatibility."""
        return self._directory

    async def find_by_id(self, shop_id: UUID, customer_id: UUID) -> CustomerProfile | None:
        return await self._directory.find_by_id(shop_id, customer_id)

    async def find_by_phone(self, shop_id: UUID, phone: str) -> list[CustomerProfile]:
        return await self._directory.find_by_phone(shop_id, phone)

    async def find_by_email(self, shop_id: UUID, email: str) -> list[CustomerProfile]:
        return await self._directory.find_by_email(shop_id, email)

    async def search(self, shop_id: UUID, query: str) -> list[CustomerProfile]:
        return await self._directory.search(shop_id, query)

    async def create(self, profile: CustomerProfile) -> CustomerProfile:
        return await self._directory.create(profile)

    async def update(self, profile: CustomerProfile) -> CustomerProfile:
        return await self._directory.update(profile)

    async def merge(
        self, shop_id: UUID, primary_id: UUID, duplicate_ids: list[UUID]
    ) -> CustomerProfile:
        return await self._directory.merge(shop_id, primary_id, duplicate_ids)

    async def summary(self, shop_id: UUID, customer_id: UUID) -> str:
        profile = await self._directory.find_by_id(shop_id, customer_id)
        if profile is None:
            return f"Customer {customer_id}: not found."
        parts = [f"Customer {profile.name} ({profile.id})"]
        if profile.phone:
            parts.append(f"phone={profile.phone}")
        if profile.email:
            parts.append(f"email={profile.email}")
        if profile.tags:
            parts.append(f"tags={','.join(profile.tags)}")
        return "; ".join(parts)
