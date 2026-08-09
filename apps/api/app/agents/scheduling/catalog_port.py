"""Read-only Service Catalog port for AI scheduling decisions.

AI may list/match services and read duration. Mutations (booking) stay
in Workflow DecisionExecutor — never write through this port.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4


@dataclass(slots=True)
class CatalogServiceView:
    """Lightweight catalog row for Decision Layer matching (no ORM)."""

    id: UUID
    name: str
    category: str
    duration_minutes: int
    skill: str
    bay: str
    active: bool = True
    price: Decimal = Decimal("0")


class ServiceCatalogPort(Protocol):
    """Read-only catalog access for SchedulingAgent."""

    async def list_bookable_services(self, shop_id: UUID) -> list[CatalogServiceView]: ...


class InMemoryServiceCatalog:
    """In-memory catalog for tests / agent runtime without a DB session."""

    def __init__(self, services: list[CatalogServiceView] | None = None) -> None:
        self._by_shop: dict[UUID, list[CatalogServiceView]] = {}
        if services:
            # shop_id unknown — store under a sentinel; use seed_shop instead
            self._orphan = list(services)
        else:
            self._orphan = []

    def seed_shop(self, shop_id: UUID, services: list[CatalogServiceView]) -> None:
        self._by_shop[shop_id] = list(services)

    def seed_from_starter(self, shop_id: UUID) -> list[CatalogServiceView]:
        """Populate from shop-setup STARTER_SERVICES (deterministic demo catalog)."""
        from app.shop_setup.defaults import STARTER_SERVICES

        views = [
            CatalogServiceView(
                id=uuid4(),
                name=str(row["name"]),
                category=str(row["category"]),
                duration_minutes=int(row["duration_minutes"]),
                skill=str(row["skill"]),
                bay=str(row["bay"]),
                active=bool(row.get("active", True)),
                price=Decimal(str(row.get("price", 0))),
            )
            for row in STARTER_SERVICES
        ]
        self.seed_shop(shop_id, views)
        return views

    async def list_bookable_services(self, shop_id: UUID) -> list[CatalogServiceView]:
        rows = self._by_shop.get(shop_id) or self._orphan
        return [s for s in rows if s.active]


class SessionServiceCatalog:
    """Adapter — reads active services from ShopSetup (Postgres). Read-only."""

    def __init__(self, session_factory) -> None:  # noqa: ANN001
        self._session_factory = session_factory

    async def list_bookable_services(self, shop_id: UUID) -> list[CatalogServiceView]:
        from sqlalchemy import text

        from app.shop_setup.service import ShopSetupService

        async with self._session_factory() as session:
            # shop_services has FORCE RLS — must bind app.shop_id or reads return []
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            svc = ShopSetupService(session)
            services = await svc.list_services(shop_id, active_only=True)
        return [
            CatalogServiceView(
                id=s.id,
                name=s.name,
                category=s.category,
                duration_minutes=s.duration_minutes,
                skill=s.skill,
                bay=s.bay,
                active=s.active,
                price=s.price,
            )
            for s in services
        ]


class CachingServiceCatalog:
    """TTL cache over a catalog port — phone turns hit the DB once, not every turn."""

    def __init__(
        self,
        inner: ServiceCatalogPort,
        *,
        ttl_sec: float = 60.0,
    ) -> None:
        self._inner = inner
        self._ttl = max(1.0, float(ttl_sec))
        self._cache: dict[UUID, tuple[float, list[CatalogServiceView]]] = {}

    def invalidate(self, shop_id: UUID | None = None) -> None:
        if shop_id is None:
            self._cache.clear()
        else:
            self._cache.pop(shop_id, None)

    async def list_bookable_services(self, shop_id: UUID) -> list[CatalogServiceView]:
        import time

        now = time.monotonic()
        hit = self._cache.get(shop_id)
        if hit is not None and (now - hit[0]) < self._ttl:
            return list(hit[1])
        rows = await self._inner.list_bookable_services(shop_id)
        self._cache[shop_id] = (now, list(rows))
        return list(rows)
