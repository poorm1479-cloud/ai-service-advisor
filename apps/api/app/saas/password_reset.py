"""Password reset tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.infrastructure.database import Base, SessionLocal
from app.infrastructure.models import UserModel
from app.infrastructure.security import hash_password
from app.saas.email import build_email_sender
from app.infrastructure.config import settings


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _hash_token(raw: str) -> str:
    import hashlib

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PasswordResetService:
    async def request_reset(self, *, email: str | None = None, phone: str | None = None) -> dict:
        from app.auth.otp import normalize_email, normalize_phone

        async with SessionLocal() as session:
            user = None
            if email:
                user = await session.scalar(
                    select(UserModel).where(UserModel.email == normalize_email(email))
                )
            elif phone:
                user = await session.scalar(
                    select(UserModel).where(UserModel.phone == normalize_phone(phone))
                )
            else:
                raise ValidationError("email or phone is required")

            # Always return ok to avoid account enumeration
            if user is None or not user.is_active:
                return {"ok": True, "dev_token": None}

            raw = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc)
            session.add(
                PasswordResetTokenModel(
                    id=uuid4(),
                    user_id=user.id,
                    token_hash=_hash_token(raw),
                    expires_at=now + timedelta(hours=1),
                    created_at=now,
                )
            )
            await session.commit()

            reset_url = f"{settings.web_app_url.rstrip('/')}/reset-password?token={raw}"
            if user.email:
                await build_email_sender().send(
                    to=user.email,
                    subject="Reset your RatchetHub password",
                    body=f"Use this link to reset your password (expires in 1 hour):\n\n{reset_url}\n",
                )
            return {
                "ok": True,
                "dev_token": raw if settings.environment in {"development", "dev", "test", "testing"} else None,
            }

    async def reset_password(self, *, token: str, new_password: str) -> None:
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        async with SessionLocal() as session:
            row = await session.scalar(
                select(PasswordResetTokenModel).where(
                    PasswordResetTokenModel.token_hash == _hash_token(token)
                )
            )
            now = datetime.now(timezone.utc)
            if row is None or row.used_at is not None or row.expires_at <= now:
                raise AuthenticationError("Invalid or expired reset token")
            user = await session.get(UserModel, row.user_id)
            if user is None or not user.is_active:
                raise NotFoundError("User not found")
            user.password_hash = hash_password(new_password)
            row.used_at = now
            await session.commit()
