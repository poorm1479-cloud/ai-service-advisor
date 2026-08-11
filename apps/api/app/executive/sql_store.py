"""SQL-backed executive dashboard store (survives API restarts).

Uses executive_snapshots / executive_live_state (Alembic 0013). Hot path keeps
an in-memory cache; hydrate on first access and flush after each refresh.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.executive.models import (
    ChartPoint,
    ChartSeries,
    DashboardCard,
    ExecutiveSnapshot,
    ShopLiveState,
    Widget,
    WidgetItem,
)
from app.executive.store import InMemoryExecutiveStore

logger = logging.getLogger("asa.executive.sql_store")


def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return str(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(_jsonable(obj), separators=(",", ":"), default=str)


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _dec(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:  # noqa: BLE001
        return Decimal(default)


def _live_from_dict(shop_id: UUID, data: dict[str, Any]) -> ShopLiveState:
    return ShopLiveState(
        shop_id=shop_id,
        todays_revenue=_dec(data.get("todays_revenue")),
        expected_revenue=_dec(data.get("expected_revenue")),
        appointments_today=int(data.get("appointments_today") or 0),
        missed_calls=int(data.get("missed_calls") or 0),
        walk_ins_today=int(data.get("walk_ins_today") or 0),
        customers_total=int(data.get("customers_total") or 0),
        ai_conversations=int(data.get("ai_conversations") or 0),
        human_escalations=int(data.get("human_escalations") or 0),
        revenue_opportunities=int(data.get("revenue_opportunities") or 0),
        marketing_roi=float(data.get("marketing_roi") or 0.0),
        customer_satisfaction=float(data.get("customer_satisfaction") or 0.0),
        mechanic_productivity=float(data.get("mechanic_productivity") or 0.0),
        version=int(data.get("version") or 1),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def _card_from_dict(d: dict[str, Any]) -> DashboardCard:
    return DashboardCard(
        id=str(d.get("id") or ""),
        label=str(d.get("label") or ""),
        value=str(d.get("value") or ""),
        delta=d.get("delta"),
        unit=d.get("unit"),
        tone=str(d.get("tone") or "neutral"),
        detail=d.get("detail"),
    )


def _point_from_dict(d: dict[str, Any]) -> ChartPoint:
    return ChartPoint(
        label=str(d.get("label") or ""),
        value=float(d.get("value") or 0),
        secondary=d.get("secondary"),
    )


def _chart_from_dict(d: dict[str, Any]) -> ChartSeries:
    return ChartSeries(
        id=str(d.get("id") or ""),
        title=str(d.get("title") or ""),
        points=[_point_from_dict(p) for p in (d.get("points") or []) if isinstance(p, dict)],
        unit=d.get("unit"),
    )


def _widget_item_from_dict(d: dict[str, Any]) -> WidgetItem:
    return WidgetItem(
        id=str(d.get("id") or ""),
        title=str(d.get("title") or ""),
        subtitle=d.get("subtitle"),
        status=d.get("status"),
        priority=str(d.get("priority") or "normal"),
        href=d.get("href"),
        meta=dict(d.get("meta") or {}),
    )


def _widget_from_dict(d: dict[str, Any]) -> Widget:
    return Widget(
        id=str(d.get("id") or ""),
        title=str(d.get("title") or ""),
        items=[
            _widget_item_from_dict(i) for i in (d.get("items") or []) if isinstance(i, dict)
        ],
    )


def _snapshot_from_dict(shop_id: UUID, data: dict[str, Any]) -> ExecutiveSnapshot:
    return ExecutiveSnapshot(
        shop_id=shop_id,
        generated_at=_parse_dt(data.get("generated_at")) or datetime.now(timezone.utc),
        version=int(data.get("version") or 1),
        cards=[_card_from_dict(c) for c in (data.get("cards") or []) if isinstance(c, dict)],
        charts=[_chart_from_dict(c) for c in (data.get("charts") or []) if isinstance(c, dict)],
        widgets=[_widget_from_dict(w) for w in (data.get("widgets") or []) if isinstance(w, dict)],
        live=dict(data.get("live") or {}),
        sources=dict(data.get("sources") or {}),
    )


class SqlExecutiveStore(InMemoryExecutiveStore):
    """In-memory hot cache + Postgres durable snapshots/live state."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        super().__init__()
        if session_factory is None:
            from app.infrastructure.database import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory
        self._hydrated: set[UUID] = set()

    async def _bind(self, session: AsyncSession, shop_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )

    async def ensure_hydrated(self, shop_id: UUID) -> None:
        if shop_id in self._hydrated:
            return
        try:
            async with self._session_factory() as session:
                await self._bind(session, shop_id)
                live_row = (
                    await session.execute(
                        text(
                            "SELECT state_json, version, updated_at "
                            "FROM executive_live_state WHERE shop_id = :shop_id"
                        ),
                        {"shop_id": shop_id},
                    )
                ).mappings().first()
                if live_row and live_row.get("state_json"):
                    payload = _loads(live_row["state_json"])
                    if isinstance(payload, dict):
                        state = _live_from_dict(shop_id, payload)
                        state.version = int(live_row.get("version") or state.version)
                        state.updated_at = live_row.get("updated_at") or state.updated_at
                        self.live[shop_id] = state

                snap_row = (
                    await session.execute(
                        text(
                            "SELECT payload_json FROM executive_snapshots "
                            "WHERE shop_id = :shop_id "
                            "ORDER BY generated_at DESC LIMIT 1"
                        ),
                        {"shop_id": shop_id},
                    )
                ).mappings().first()
                if snap_row and snap_row.get("payload_json"):
                    payload = _loads(snap_row["payload_json"])
                    if isinstance(payload, dict):
                        self.snapshots[shop_id] = _snapshot_from_dict(shop_id, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("executive.hydrate_failed shop=%s err=%s", shop_id, exc)
        self._hydrated.add(shop_id)

    async def persist(self, shop_id: UUID) -> None:
        live = self.live.get(shop_id)
        snapshot = self.snapshots.get(shop_id)
        if live is None and snapshot is None:
            return
        try:
            async with self._session_factory() as session:
                await self._bind(session, shop_id)
                if live is not None:
                    await session.execute(
                        text(
                            """
                            INSERT INTO executive_live_state (
                                shop_id, version, state_json, updated_at
                            ) VALUES (
                                :shop_id, :version, :state_json, :updated_at
                            )
                            ON CONFLICT (shop_id) DO UPDATE SET
                                version = EXCLUDED.version,
                                state_json = EXCLUDED.state_json,
                                updated_at = EXCLUDED.updated_at
                            """
                        ),
                        {
                            "shop_id": shop_id,
                            "version": int(live.version or 1),
                            "state_json": _dumps(live),
                            "updated_at": live.updated_at or datetime.now(timezone.utc),
                        },
                    )
                if snapshot is not None:
                    # Keep one row per shop (replace latest) to avoid unbounded growth.
                    await session.execute(
                        text("DELETE FROM executive_snapshots WHERE shop_id = :shop_id"),
                        {"shop_id": shop_id},
                    )
                    await session.execute(
                        text(
                            """
                            INSERT INTO executive_snapshots (
                                id, shop_id, version, payload_json, generated_at, created_at
                            ) VALUES (
                                :id, :shop_id, :version, :payload_json, :generated_at, :created_at
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "shop_id": shop_id,
                            "version": int(snapshot.version or 1),
                            "payload_json": _dumps(snapshot),
                            "generated_at": snapshot.generated_at,
                            "created_at": datetime.now(timezone.utc),
                        },
                    )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("executive.persist_failed shop=%s err=%s", shop_id, exc)


def build_default_executive_store() -> InMemoryExecutiveStore:
    """SQL-backed store outside tests so dashboard KPIs survive API restarts."""
    try:
        from app.infrastructure.config import settings

        if settings.environment.lower() in {"test", "testing"}:
            return InMemoryExecutiveStore()
        from app.infrastructure.database import SessionLocal

        return SqlExecutiveStore(SessionLocal)
    except Exception:  # pragma: no cover
        return InMemoryExecutiveStore()
