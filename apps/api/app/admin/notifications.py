"""Durable platform-admin notification storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, delete, select, update
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base, SessionLocal

# Platform-scoped events (no tenant shop) use the nil UUID.
PLATFORM_SHOP_ID = UUID("00000000-0000-0000-0000-000000000000")


class AdminNotificationModel(Base):
    __tablename__ = "admin_notifications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    shop_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unread", index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(slots=True)
class AdminNotification:
    id: UUID
    event_type: str
    source: str
    severity: str
    title: str
    message: str
    shop_id: UUID | None
    payload: dict[str, Any]
    status: str
    dedupe_key: str | None
    occurred_at: datetime
    read_at: datetime | None
    created_at: datetime

    def to_feed_item(self) -> dict[str, Any]:
        payload = self.payload if isinstance(self.payload, dict) else {}
        slug = payload.get("shop_slug") or payload.get("slug") or None
        if slug is not None:
            slug = str(slug) or None
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "source": self.source,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "shop_id": str(self.shop_id) if self.shop_id and self.shop_id != PLATFORM_SHOP_ID else None,
            "shop_slug": slug,
            "payload": self.payload,
            "status": self.status,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


def _to_domain(m: AdminNotificationModel) -> AdminNotification:
    try:
        payload = json.loads(m.payload_json or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return AdminNotification(
        id=m.id,
        event_type=m.event_type,
        source=m.source,
        severity=m.severity,
        title=m.title,
        message=m.message,
        shop_id=m.shop_id,
        payload=payload,
        status=m.status,
        dedupe_key=m.dedupe_key,
        occurred_at=m.occurred_at,
        read_at=m.read_at,
        created_at=m.created_at,
    )


class AdminNotificationService:
    async def create(
        self,
        *,
        event_type: str,
        title: str,
        message: str = "",
        severity: str = "info",
        source: str = "system",
        shop_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
        occurred_at: datetime | None = None,
    ) -> AdminNotification | None:
        now = datetime.now(timezone.utc)
        row = AdminNotificationModel(
            id=uuid4(),
            event_type=event_type,
            source=source,
            severity=severity,
            title=title.strip()[:200],
            message=(message or "").strip(),
            shop_id=shop_id,
            payload_json=json.dumps(payload or {}, default=str),
            status="unread",
            dedupe_key=dedupe_key,
            occurred_at=occurred_at or now,
            created_at=now,
        )
        async with SessionLocal() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return None
            await session.refresh(row)
            return _to_domain(row)

    async def list(
        self,
        *,
        limit: int = 200,
        event_type: str | None = None,
        status: str | None = None,
        unread_only: bool = False,
    ) -> list[AdminNotification]:
        async with SessionLocal() as session:
            stmt = select(AdminNotificationModel).order_by(
                AdminNotificationModel.occurred_at.desc()
            )
            if event_type:
                stmt = stmt.where(AdminNotificationModel.event_type == event_type)
            if status:
                stmt = stmt.where(AdminNotificationModel.status == status)
            elif unread_only:
                stmt = stmt.where(AdminNotificationModel.status == "unread")
            stmt = stmt.limit(limit)
            rows = (await session.scalars(stmt)).all()
            return [_to_domain(r) for r in rows]

    async def counts(self) -> dict[str, Any]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(
                        AdminNotificationModel.event_type,
                        AdminNotificationModel.status,
                    )
                )
            ).all()
        by_type: dict[str, int] = {}
        unread = 0
        for et, st in rows:
            by_type[et] = by_type.get(et, 0) + 1
            if st == "unread":
                unread += 1
        return {"total": len(rows), "unread": unread, "by_event_type": by_type}

    async def mark_read(self, notification_id: UUID) -> AdminNotification | None:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as session:
            row = await session.get(AdminNotificationModel, notification_id)
            if row is None:
                return None
            if row.status != "read":
                row.status = "read"
                row.read_at = now
                await session.commit()
                await session.refresh(row)
            return _to_domain(row)

    async def delete(self, notification_id: UUID) -> bool:
        async with SessionLocal() as session:
            result = await session.execute(
                delete(AdminNotificationModel).where(AdminNotificationModel.id == notification_id)
            )
            await session.commit()
            return int(result.rowcount or 0) > 0

    async def delete_many(self, notification_ids: list[UUID]) -> int:
        if not notification_ids:
            return 0
        async with SessionLocal() as session:
            result = await session.execute(
                delete(AdminNotificationModel).where(AdminNotificationModel.id.in_(notification_ids))
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def mark_all_read(self) -> int:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as session:
            result = await session.execute(
                update(AdminNotificationModel)
                .where(AdminNotificationModel.status == "unread")
                .values(status="read", read_at=now)
            )
            await session.commit()
            return int(result.rowcount or 0)
