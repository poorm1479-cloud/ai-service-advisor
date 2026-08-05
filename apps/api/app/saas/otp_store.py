"""Durable OTP challenge store (PostgreSQL)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.otp import OtpChallenge
from app.infrastructure.database import Base, SessionLocal


class AuthOtpChallengeModel(Base):
    __tablename__ = "auth_otp_challenges"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str] = mapped_column(String(320), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _to_domain(m: AuthOtpChallengeModel) -> OtpChallenge:
    return OtpChallenge(
        id=m.id,
        target=m.target,
        channel=m.channel,
        purpose=m.purpose,
        code_hash=m.code_hash,
        expires_at=m.expires_at,
        attempts=m.attempts,
        consumed_at=m.consumed_at,
        created_at=m.created_at,
    )


class SqlAlchemyOtpStore:
    async def save(self, challenge: OtpChallenge) -> OtpChallenge:
        async with SessionLocal() as session:
            # deactivate previous active rows for same key
            rows = (
                await session.scalars(
                    select(AuthOtpChallengeModel).where(
                        AuthOtpChallengeModel.channel == challenge.channel,
                        AuthOtpChallengeModel.target == challenge.target,
                        AuthOtpChallengeModel.purpose == challenge.purpose,
                        AuthOtpChallengeModel.consumed_at.is_(None),
                    )
                )
            ).all()
            now = challenge.created_at
            for row in rows:
                row.consumed_at = now
            session.add(
                AuthOtpChallengeModel(
                    id=challenge.id,
                    channel=challenge.channel,
                    target=challenge.target,
                    purpose=challenge.purpose,
                    code_hash=challenge.code_hash,
                    expires_at=challenge.expires_at,
                    attempts=challenge.attempts,
                    consumed_at=challenge.consumed_at,
                    created_at=challenge.created_at,
                )
            )
            await session.commit()
        return challenge

    async def get_active(self, channel: str, target: str, purpose: str) -> OtpChallenge | None:
        async with SessionLocal() as session:
            row = await session.scalar(
                select(AuthOtpChallengeModel)
                .where(
                    AuthOtpChallengeModel.channel == channel,
                    AuthOtpChallengeModel.target == target,
                    AuthOtpChallengeModel.purpose == purpose,
                    AuthOtpChallengeModel.consumed_at.is_(None),
                )
                .order_by(AuthOtpChallengeModel.created_at.desc())
            )
            return _to_domain(row) if row else None

    async def update(self, challenge: OtpChallenge) -> OtpChallenge:
        async with SessionLocal() as session:
            row = await session.get(AuthOtpChallengeModel, challenge.id)
            if row is None:
                return challenge
            row.attempts = challenge.attempts
            row.consumed_at = challenge.consumed_at
            row.code_hash = challenge.code_hash
            row.expires_at = challenge.expires_at
            await session.commit()
        return challenge
