from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories import (
    SqlAlchemyCommunicationHistoryRepository,
    SqlAlchemyCustomerRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyRefreshTokenRepository,
    SqlAlchemyRepairHistoryRepository,
    SqlAlchemyShopRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyVehicleRepository,
    SqlAlchemyVoiceNoteRepository,
    SqlAlchemyWalkInVisitRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.shops = SqlAlchemyShopRepository(session)
        self.users = SqlAlchemyUserRepository(session)
        self.memberships = SqlAlchemyMembershipRepository(session)
        self.refresh_tokens = SqlAlchemyRefreshTokenRepository(session)
        self.customers = SqlAlchemyCustomerRepository(session)
        self.vehicles = SqlAlchemyVehicleRepository(session)
        self.repair_histories = SqlAlchemyRepairHistoryRepository(session)
        self.communications = SqlAlchemyCommunicationHistoryRepository(session)
        self.walk_ins = SqlAlchemyWalkInVisitRepository(session)
        self.voice_notes = SqlAlchemyVoiceNoteRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def bind_shop(self, shop_id: UUID) -> None:
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
