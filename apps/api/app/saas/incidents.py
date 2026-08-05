"""Public status incidents for the status page timeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base, SessionLocal


class StatusIncidentModel(Base):
    __tablename__ = "status_incidents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="minor")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="investigating")
    affected_components: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(slots=True)
class StatusIncident:
    id: UUID
    title: str
    summary: str
    severity: str
    status: str
    affected_components: list[str]
    started_at: datetime
    resolved_at: datetime | None


def _to_domain(m: StatusIncidentModel) -> StatusIncident:
    try:
        comps = json.loads(m.affected_components or "[]")
        if not isinstance(comps, list):
            comps = []
    except (TypeError, ValueError, json.JSONDecodeError):
        comps = []
    return StatusIncident(
        id=m.id,
        title=m.title,
        summary=m.summary,
        severity=m.severity,
        status=m.status,
        affected_components=[str(c) for c in comps],
        started_at=m.started_at,
        resolved_at=m.resolved_at,
    )


class StatusIncidentService:
    async def list_public(self, *, limit: int = 20) -> list[StatusIncident]:
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(StatusIncidentModel)
                    .order_by(StatusIncidentModel.started_at.desc())
                    .limit(limit)
                )
            ).all()
            return [_to_domain(r) for r in rows]

    async def create(
        self,
        *,
        title: str,
        summary: str = "",
        severity: str = "minor",
        status: str = "investigating",
        affected_components: list[str] | None = None,
    ) -> StatusIncident:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as session:
            row = StatusIncidentModel(
                id=uuid4(),
                title=title.strip(),
                summary=summary.strip(),
                severity=severity,
                status=status,
                affected_components=json.dumps(list(affected_components or [])),
                started_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            incident = _to_domain(row)
        sev = (severity or "minor").lower()
        if sev in {"critical", "major"}:
            try:
                from app.admin.notifications import PLATFORM_SHOP_ID
                from app.workflows.emitter import emit_domain_event
                from app.workflows.enums import DomainEventType

                await emit_domain_event(
                    shop_id=PLATFORM_SHOP_ID,
                    event_type=DomainEventType.SYSTEM_ERROR,
                    payload={
                        "incident_id": str(incident.id),
                        "title": incident.title,
                        "summary": incident.summary,
                        "severity": "critical" if sev == "critical" else "major",
                        "status": incident.status,
                        "affected_components": incident.affected_components,
                    },
                    source="incidents",
                )
            except Exception:
                pass
        return incident

    async def update(
        self,
        incident_id: UUID,
        *,
        status: str | None = None,
        summary: str | None = None,
        resolve: bool = False,
    ) -> StatusIncident | None:
        async with SessionLocal() as session:
            row = await session.get(StatusIncidentModel, incident_id)
            if row is None:
                return None
            now = datetime.now(timezone.utc)
            if status is not None:
                row.status = status
            if summary is not None:
                row.summary = summary
            if resolve or status == "resolved":
                row.status = "resolved"
                row.resolved_at = now
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)
