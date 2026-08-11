"""Load revenue-intel CustomerSnapshots from durable CRM tables."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.revenue_intel.models import (
    CommunicationSnapshot,
    CustomerSnapshot,
    RepairSnapshot,
    VehicleSnapshot,
)

logger = logging.getLogger("asa.revenue_intel.crm_sync")


async def load_customer_snapshots_from_crm(
    shop_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    limit: int = 500,
) -> list[CustomerSnapshot]:
    """Build CustomerSnapshot list from customers/vehicles/repairs/comms (RLS)."""
    if session_factory is None:
        from app.infrastructure.database import SessionLocal

        session_factory = SessionLocal

    from app.infrastructure.models import (
        CommunicationHistoryModel,
        CustomerModel,
        RepairHistoryModel,
        VehicleModel,
    )

    try:
        async with session_factory() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            customers = (
                (
                    await session.execute(
                        select(CustomerModel)
                        .where(CustomerModel.shop_id == shop_id)
                        .order_by(CustomerModel.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            if not customers:
                return []

            customer_ids = [c.id for c in customers]
            vehicles = (
                (
                    await session.execute(
                        select(VehicleModel).where(
                            VehicleModel.shop_id == shop_id,
                            VehicleModel.customer_id.in_(customer_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            vehicle_ids = [v.id for v in vehicles]
            repairs: list[Any] = []
            if vehicle_ids:
                repairs = (
                    (
                        await session.execute(
                            select(RepairHistoryModel)
                            .where(
                                RepairHistoryModel.shop_id == shop_id,
                                RepairHistoryModel.vehicle_id.in_(vehicle_ids),
                            )
                            .order_by(RepairHistoryModel.created_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
            comms = (
                (
                    await session.execute(
                        select(CommunicationHistoryModel)
                        .where(
                            CommunicationHistoryModel.shop_id == shop_id,
                            CommunicationHistoryModel.customer_id.in_(customer_ids),
                        )
                        .order_by(CommunicationHistoryModel.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("revenue_intel.crm_sync_failed shop=%s err=%s", shop_id, exc)
        return []

    vehicles_by_customer: dict[UUID, list[VehicleModel]] = defaultdict(list)
    for v in vehicles:
        if v.customer_id:
            vehicles_by_customer[v.customer_id].append(v)

    repairs_by_vehicle: dict[UUID, list[RepairHistoryModel]] = defaultdict(list)
    for r in repairs:
        repairs_by_vehicle[r.vehicle_id].append(r)

    comms_by_customer: dict[UUID, list[CommunicationHistoryModel]] = defaultdict(list)
    for c in comms:
        comms_by_customer[c.customer_id].append(c)

    out: list[CustomerSnapshot] = []
    for cust in customers:
        v_snaps: list[VehicleSnapshot] = []
        total_spend = Decimal("0")
        visit_times: list[datetime] = []
        declined: list[dict[str, Any]] = []

        for veh in vehicles_by_customer.get(cust.id, []):
            r_snaps: list[RepairSnapshot] = []
            for rep in repairs_by_vehicle.get(veh.id, []):
                cost = Decimal(str(rep.cost or 0))
                total_spend += cost
                performed = rep.created_at
                if performed is not None and performed.tzinfo is None:
                    performed = performed.replace(tzinfo=timezone.utc)
                if performed is not None:
                    visit_times.append(performed)
                recommendation = (rep.recommendation or "").strip() or None
                r_snaps.append(
                    RepairSnapshot(
                        service_type=str(rep.service_type or "general"),
                        description=str(rep.description or ""),
                        cost=cost,
                        mileage=veh.mileage,
                        performed_at=performed,
                        recommendation=recommendation,
                        declined=False,
                    )
                )
                if recommendation:
                    declined.append(
                        {
                            "service": str(rep.service_type or ""),
                            "amount": str(cost),
                            "recommendation": recommendation,
                        }
                    )
            v_snaps.append(
                VehicleSnapshot(
                    id=veh.id,
                    vin=str(veh.vin or ""),
                    year=int(veh.year or 0),
                    make=str(veh.make or ""),
                    model=str(veh.model or ""),
                    mileage=int(veh.mileage or 0),
                    license_plate=veh.license_plate,
                    repairs=r_snaps,
                )
            )

        c_snaps = [
            CommunicationSnapshot(
                channel=str(m.channel or "sms"),
                direction=str(m.direction or "outbound"),
                message=str(m.message or ""),
                occurred_at=(
                    m.created_at.replace(tzinfo=timezone.utc)
                    if m.created_at is not None and m.created_at.tzinfo is None
                    else m.created_at
                ),
            )
            for m in comms_by_customer.get(cust.id, [])[:40]
        ]

        first_visit = min(visit_times) if visit_times else cust.created_at
        last_visit = max(visit_times) if visit_times else cust.created_at
        if first_visit is not None and first_visit.tzinfo is None:
            first_visit = first_visit.replace(tzinfo=timezone.utc)
        if last_visit is not None and last_visit.tzinfo is None:
            last_visit = last_visit.replace(tzinfo=timezone.utc)

        out.append(
            CustomerSnapshot(
                id=cust.id,
                shop_id=shop_id,
                name=str(cust.name or "Customer"),
                phone=cust.phone,
                email=cust.email,
                vehicles=v_snaps,
                communications=c_snaps,
                declined_estimates=declined[:20],
                last_visit_at=last_visit,
                first_visit_at=first_visit,
                total_spend=total_spend.quantize(Decimal("0.01")),
                visit_count=len(visit_times),
            )
        )
    return out


async def sync_revenue_intel_customers_from_crm(
    store: Any,
    shop_id: UUID,
    *,
    force: bool = False,
) -> int:
    """Upsert CRM customers into an in-memory (or compatible) revenue intel store."""
    if hasattr(store, "ensure_shop"):
        store.ensure_shop(shop_id)
    existing = await store.list_customers(shop_id)
    if existing and not force:
        return len(existing)
    snapshots = await load_customer_snapshots_from_crm(shop_id)
    if not snapshots:
        return 0
    # Replace shop bucket when store is in-memory so stale demos don't linger.
    if hasattr(store, "customers") and isinstance(getattr(store, "customers"), dict):
        store.customers[shop_id] = snapshots
        return len(snapshots)
    for snap in snapshots:
        await store.upsert_customer(snap)
    return len(snapshots)
