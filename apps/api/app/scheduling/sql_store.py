"""SQL-backed appointment persistence for Schedule / voice / SMS bookings.

Mechanics, bays, and hours stay in the in-memory shop resource store (synced
from Team + shop setup). Appointments are dual-written to Postgres so they
survive restarts and remain visible on the dashboard after voice books them.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scheduling.engines.availability import DEFAULT_SHOP_TZ
from app.scheduling.enums import AppointmentStatus
from app.scheduling.models import Appointment
from app.scheduling.store import InMemoryShopResourceStore, ShopResourcePort

logger = logging.getLogger("asa.scheduling.sql_store")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_shop(
    value: datetime | None,
    *,
    shop_tz: ZoneInfo = DEFAULT_SHOP_TZ,
) -> datetime | None:
    """Hydrate DB timestamps as shop wall-clock (API / calendar display contract).

    Postgres stores UTC; returning UTC hour digits makes the dashboard treat
    3:00 PM LA as 10:00 PM (wallClockParts reads ISO digits, not absolute time).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        # timestamptz drivers usually hand back aware UTC; treat bare as UTC.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(shop_tz)


def _row_to_appointment(row: Any) -> Appointment:
    meta: dict[str, Any] = {}
    raw_meta = row.get("metadata_json") if isinstance(row, dict) else row.metadata_json
    if raw_meta:
        try:
            parsed = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
            if isinstance(parsed, dict):
                meta = parsed
        except (TypeError, json.JSONDecodeError):
            meta = {}
    start = row["start_at"] if isinstance(row, dict) else row.start_at
    end = row["end_at"] if isinstance(row, dict) else row.end_at
    mechanic_id = row["mechanic_id"] if isinstance(row, dict) else row.mechanic_id
    bay_id = row["bay_id"] if isinstance(row, dict) else row.bay_id
    # Recover Team mechanic/bay ids when SQL FKs had to be nulled on write.
    if mechanic_id is None and meta.get("mechanic_id"):
        try:
            mechanic_id = UUID(str(meta["mechanic_id"]))
        except (TypeError, ValueError):
            pass
    if bay_id is None and meta.get("bay_id"):
        try:
            bay_id = UUID(str(meta["bay_id"]))
        except (TypeError, ValueError):
            pass
    return Appointment(
        id=row["id"] if isinstance(row, dict) else row.id,
        shop_id=row["shop_id"] if isinstance(row, dict) else row.shop_id,
        start=_as_shop(start) or datetime.now(DEFAULT_SHOP_TZ),
        end=_as_shop(end) or datetime.now(DEFAULT_SHOP_TZ),
        status=str(row["status"] if isinstance(row, dict) else row.status),
        priority=str(row["priority"] if isinstance(row, dict) else row.priority),
        repair_type=str(
            row["repair_type"] if isinstance(row, dict) else row.repair_type
        ),
        vehicle_type=str(
            row["vehicle_type"] if isinstance(row, dict) else row.vehicle_type
        ),
        estimated_duration_min=int(
            row["estimated_duration_min"]
            if isinstance(row, dict)
            else row.estimated_duration_min
        ),
        service_id=row["service_id"] if isinstance(row, dict) else row.service_id,
        customer_id=row["customer_id"] if isinstance(row, dict) else row.customer_id,
        vehicle_id=row["vehicle_id"] if isinstance(row, dict) else row.vehicle_id,
        mechanic_id=mechanic_id,
        bay_id=bay_id,
        walk_in_id=row["walk_in_id"] if isinstance(row, dict) else row.walk_in_id,
        source=str(row["source"] if isinstance(row, dict) else row.source),
        notes=row["notes"] if isinstance(row, dict) else row.notes,
        estimated_revenue=Decimal(
            str(
                row["estimated_revenue"]
                if isinstance(row, dict)
                else row.estimated_revenue
            )
        ),
        estimated_completion=_as_shop(
            row["estimated_completion"]
            if isinstance(row, dict)
            else row.estimated_completion
        ),
        wait_time_min=row["wait_time_min"]
        if isinstance(row, dict)
        else row.wait_time_min,
        created_at=_as_shop(
            row["created_at"] if isinstance(row, dict) else row.created_at
        )
        or datetime.now(DEFAULT_SHOP_TZ),
        metadata=meta,
    )


class SqlShopResourceStore(InMemoryShopResourceStore):
    """Shop resources in memory; appointments dual-written to Postgres."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        super().__init__()
        if session_factory is None:
            from app.infrastructure.database import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    async def _bind(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )

    async def list_appointments(
        self,
        shop_id: UUID,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
    ) -> list[Appointment]:
        self.ensure_shop(shop_id)
        try:
            async with self._session_factory() as session:
                await self._bind(session, shop_id)
                clauses = ["shop_id = :shop_id"]
                params: dict[str, Any] = {"shop_id": shop_id}
                if start is not None:
                    clauses.append("end_at > :start")
                    params["start"] = _as_utc(start)
                if end is not None:
                    clauses.append("start_at < :end")
                    params["end"] = _as_utc(end)
                if status:
                    clauses.append("status = :status")
                    params["status"] = status
                else:
                    clauses.append(
                        "status NOT IN ('cancelled', 'rescheduled')"
                    )
                sql = (
                    "SELECT * FROM appointments WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY start_at ASC"
                )
                result = await session.execute(text(sql), params)
                rows = result.mappings().all()
                items = [_row_to_appointment(dict(r)) for r in rows]
        except Exception as exc:  # noqa: BLE001 — fall back to process memory
            logger.warning("scheduling.sql_list_failed shop=%s err=%s", shop_id, exc)
            return await super().list_appointments(
                shop_id, start=start, end=end, status=status
            )
        # Mirror into memory so capacity checks in this process stay hot.
        for appt in items:
            self.appointments[appt.id] = appt
            if appt.id not in self._by_shop[shop_id]:
                self._by_shop[shop_id].append(appt.id)
        return items

    async def get_appointment(
        self, shop_id: UUID, appointment_id: UUID
    ) -> Appointment | None:
        self.ensure_shop(shop_id)
        try:
            async with self._session_factory() as session:
                await self._bind(session, shop_id)
                result = await session.execute(
                    text(
                        "SELECT * FROM appointments "
                        "WHERE shop_id = :shop_id AND id = :id"
                    ),
                    {"shop_id": shop_id, "id": appointment_id},
                )
                row = result.mappings().first()
                if row is None:
                    return await super().get_appointment(shop_id, appointment_id)
                appt = _row_to_appointment(dict(row))
                self.appointments[appt.id] = appt
                if appt.id not in self._by_shop[shop_id]:
                    self._by_shop[shop_id].append(appt.id)
                return appt
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "scheduling.sql_get_failed shop=%s id=%s err=%s",
                shop_id,
                appointment_id,
                exc,
            )
            return await super().get_appointment(shop_id, appointment_id)

    async def save_appointment(self, appointment: Appointment) -> Appointment:
        self.ensure_shop(appointment.shop_id)
        # Keep local copy for capacity engines running in this process.
        await super().save_appointment(appointment)
        await self._upsert_sql(appointment)
        return appointment

    async def update_appointment(self, appointment: Appointment) -> Appointment:
        await super().update_appointment(appointment)
        await self._upsert_sql(appointment)
        return appointment

    async def _upsert_sql(self, appointment: Appointment) -> None:
        """Persist appointment. Soften mechanic/bay FKs when Team ids are memory-only."""
        try:
            async with self._session_factory() as session:
                await self._bind(session, appointment.shop_id)
                base = {
                    "id": appointment.id,
                    "shop_id": appointment.shop_id,
                    "customer_id": appointment.customer_id,
                    "vehicle_id": appointment.vehicle_id,
                    "walk_in_id": appointment.walk_in_id,
                    "start_at": _as_utc(appointment.start),
                    "end_at": _as_utc(appointment.end),
                    "status": appointment.status or AppointmentStatus.BOOKED.value,
                    "priority": appointment.priority or "normal",
                    "repair_type": appointment.repair_type or "general",
                    "vehicle_type": appointment.vehicle_type or "sedan",
                    "estimated_duration_min": int(
                        appointment.estimated_duration_min or 60
                    ),
                    "source": appointment.source or "agent",
                    "notes": appointment.notes,
                    "estimated_revenue": appointment.estimated_revenue
                    or Decimal("0"),
                    "estimated_completion": _as_utc(appointment.estimated_completion),
                    "wait_time_min": appointment.wait_time_min,
                    "service_id": appointment.service_id,
                }
                meta = dict(appointment.metadata or {})
                if appointment.mechanic_id:
                    meta.setdefault("mechanic_id", str(appointment.mechanic_id))
                if appointment.bay_id:
                    meta.setdefault("bay_id", str(appointment.bay_id))

                # Try full FK first; if seed/memory mechanic or bay id is not in
                # Postgres tables, retry without those FKs (ids stay in metadata).
                attempts: list[tuple[UUID | None, UUID | None]] = [
                    (appointment.mechanic_id, appointment.bay_id),
                    (appointment.mechanic_id, None),
                    (None, None),
                ]
                last_exc: Exception | None = None
                for mech_id, bay_id in attempts:
                    payload = {
                        **base,
                        "mechanic_id": mech_id,
                        "bay_id": bay_id,
                        "metadata_json": json.dumps(meta),
                    }
                    try:
                        await session.execute(
                            text(
                                """
                                INSERT INTO appointments (
                                    id, shop_id, customer_id, vehicle_id, mechanic_id, bay_id,
                                    walk_in_id, start_at, end_at, status, priority, repair_type,
                                    vehicle_type, estimated_duration_min, source, notes,
                                    estimated_revenue, estimated_completion, wait_time_min,
                                    metadata_json, service_id
                                ) VALUES (
                                    :id, :shop_id, :customer_id, :vehicle_id, :mechanic_id, :bay_id,
                                    :walk_in_id, :start_at, :end_at, :status, :priority, :repair_type,
                                    :vehicle_type, :estimated_duration_min, :source, :notes,
                                    :estimated_revenue, :estimated_completion, :wait_time_min,
                                    :metadata_json, :service_id
                                )
                                ON CONFLICT (id) DO UPDATE SET
                                    customer_id = EXCLUDED.customer_id,
                                    vehicle_id = EXCLUDED.vehicle_id,
                                    mechanic_id = EXCLUDED.mechanic_id,
                                    bay_id = EXCLUDED.bay_id,
                                    walk_in_id = EXCLUDED.walk_in_id,
                                    start_at = EXCLUDED.start_at,
                                    end_at = EXCLUDED.end_at,
                                    status = EXCLUDED.status,
                                    priority = EXCLUDED.priority,
                                    repair_type = EXCLUDED.repair_type,
                                    vehicle_type = EXCLUDED.vehicle_type,
                                    estimated_duration_min = EXCLUDED.estimated_duration_min,
                                    source = EXCLUDED.source,
                                    notes = EXCLUDED.notes,
                                    estimated_revenue = EXCLUDED.estimated_revenue,
                                    estimated_completion = EXCLUDED.estimated_completion,
                                    wait_time_min = EXCLUDED.wait_time_min,
                                    metadata_json = EXCLUDED.metadata_json,
                                    service_id = EXCLUDED.service_id
                                """
                            ),
                            payload,
                        )
                        await session.commit()
                        return
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        await session.rollback()
                        await self._bind(session, appointment.shop_id)
                        continue
                logger.error(
                    "scheduling.sql_upsert_failed id=%s shop=%s err=%s",
                    appointment.id,
                    appointment.shop_id,
                    last_exc,
                )
                if last_exc is not None:
                    raise last_exc
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "scheduling.sql_upsert_failed id=%s shop=%s err=%s",
                appointment.id,
                appointment.shop_id,
                exc,
            )
            raise


def build_default_shop_resource_store() -> ShopResourcePort:
    """Use SQL-backed store outside tests so voice bookings hit the Schedule UI."""
    try:
        from app.infrastructure.config import settings

        if settings.environment.lower() in {"test", "testing"}:
            return InMemoryShopResourceStore()
        from app.infrastructure.database import SessionLocal

        return SqlShopResourceStore(SessionLocal)
    except Exception:  # pragma: no cover
        return InMemoryShopResourceStore()
