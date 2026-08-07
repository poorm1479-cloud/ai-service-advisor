"""Resolve marketing audiences from real shop CRM / appointments / memory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.domain.entities import Customer, RepairHistory, Vehicle
from app.infrastructure.models import RepairHistoryModel, VehicleModel
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.marketing.enums import CampaignType, Channel
from app.marketing.models import AudienceMember
from app.memory.enums import MemoryCategory
from app.memory.factory import get_memory_runtime
from app.revenue_intel.catalog import SERVICE_ALIASES, SERVICE_CATALOG
from app.scheduling.enums import AppointmentStatus
from app.scheduling.factory import get_scheduling_runtime
from app.scheduling.models import Appointment

INACTIVE_DAYS = 90
THANK_YOU_DAYS = 30
MISSED_APPOINTMENT_DAYS = 90

_DECLINED_MARKERS = ("declined", "decline", "turned down", "not approved", "customer declined")


@dataclass(slots=True)
class SuggestedActionCount:
    id: str
    campaign_type: str
    title: str
    description: str
    count: int
    custom_message: str | None = None


SUGGESTED_ACTION_DEFS: list[dict[str, Any]] = [
    {
        "id": "declined_estimate",
        "campaign_type": CampaignType.DECLINED_ESTIMATE.value,
        "title": "Declined estimates",
        "description": "Customers who turned down a repair estimate — follow up while the need is fresh.",
    },
    {
        "id": "inactive_customer",
        "campaign_type": CampaignType.INACTIVE_CUSTOMER.value,
        "title": "Inactive customers",
        "description": "Haven't visited in months. Invite them back with a simple inspection offer.",
    },
    {
        "id": "maintenance_reminder",
        "campaign_type": CampaignType.MAINTENANCE_REMINDER.value,
        "title": "Maintenance reminders",
        "description": "Vehicles due for oil, brakes, or other scheduled service.",
    },
    {
        "id": "missed_appointment",
        "campaign_type": CampaignType.THANK_YOU.value,
        "title": "Missed appointments",
        "description": "No-shows who need a quick reschedule nudge.",
        "custom_message": (
            "Hi {name}, we noticed you missed your appointment for {service} on your {vehicle}. "
            "Reply YES to reschedule at {shop}."
        ),
        "segment": "missed_appointment",
    },
]


@dataclass
class _ShopAudienceContext:
    shop_id: UUID
    shop_name: str
    customers: dict[UUID, Customer]
    vehicles_by_customer: dict[UUID, list[Vehicle]] = field(default_factory=dict)
    vehicles_by_id: dict[UUID, Vehicle] = field(default_factory=dict)
    repairs: list[RepairHistory] = field(default_factory=list)
    walk_ins: list[Any] = field(default_factory=list)
    appointments: list[Appointment] = field(default_factory=list)
    declined_memory_customer_ids: set[UUID] = field(default_factory=set)
    # Precomputed max activity timestamp per customer — avoids O(C×(R+W+A)) when resolving inactive.
    last_activity_by_customer: dict[UUID, datetime] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _map_vehicle(row: VehicleModel) -> Vehicle:
    return Vehicle(
        id=row.id,
        shop_id=row.shop_id,
        customer_id=row.customer_id,
        vin=row.vin,
        license_plate=row.license_plate,
        year=row.year,
        make=row.make,
        model=row.model,
        mileage=row.mileage,
        created_at=row.created_at,
    )


def _map_repair(row: RepairHistoryModel) -> RepairHistory:
    return RepairHistory(
        id=row.id,
        shop_id=row.shop_id,
        customer_id=row.customer_id,
        vehicle_id=row.vehicle_id,
        service_type=row.service_type,
        description=row.description,
        cost=row.cost,
        recommendation=row.recommendation,
        created_at=row.created_at,
    )


def _vehicle_label(vehicle: Vehicle | None) -> str:
    if vehicle is None:
        return "your vehicle"
    return f"{vehicle.year} {vehicle.make} {vehicle.model}".strip()


def _normalize_service_key(service_type: str) -> str | None:
    key = service_type.strip().lower().replace(" ", "_").replace("-", "_")
    if key in SERVICE_CATALOG:
        return key
    return SERVICE_ALIASES.get(key) or SERVICE_ALIASES.get(service_type.strip().lower())


def _looks_declined(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _DECLINED_MARKERS)


def _to_member(
    *,
    customer: Customer,
    shop_name: str,
    vehicle: Vehicle | None = None,
    service: str | None = None,
    preferred_channel: Channel | None = None,
    extra: dict[str, Any] | None = None,
) -> AudienceMember:
    metadata: dict[str, Any] = {
        "shop": shop_name,
        "vehicle": _vehicle_label(vehicle),
        "service": service or "service",
    }
    if extra:
        metadata.update(extra)
    return AudienceMember(
        customer_id=customer.id,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        preferred_channel=preferred_channel
        or (Channel.EMAIL if customer.email and not customer.phone else Channel.SMS),
        metadata=metadata,
    )


def _dedupe(members: list[AudienceMember]) -> list[AudienceMember]:
    seen: set[UUID] = set()
    out: list[AudienceMember] = []
    for member in members:
        if member.customer_id in seen:
            continue
        seen.add(member.customer_id)
        out.append(member)
    return out


async def _load_context(uow: SqlAlchemyUnitOfWork, shop_id: UUID) -> _ShopAudienceContext:
    await uow.bind_shop(shop_id)
    shop = await uow.shops.get_by_id(shop_id)
    shop_name = shop.name if shop else "your shop"
    customers = {c.id: c for c in await uow.customers.list_by_shop(shop_id)}

    vehicle_rows = list(
        await uow._session.scalars(select(VehicleModel).where(VehicleModel.shop_id == shop_id))
    )
    vehicles_by_customer: dict[UUID, list[Vehicle]] = {}
    vehicles_by_id: dict[UUID, Vehicle] = {}
    for row in vehicle_rows:
        vehicle = _map_vehicle(row)
        vehicles_by_id[vehicle.id] = vehicle
        if vehicle.customer_id:
            vehicles_by_customer.setdefault(vehicle.customer_id, []).append(vehicle)

    repair_rows = list(
        await uow._session.scalars(
            select(RepairHistoryModel).where(RepairHistoryModel.shop_id == shop_id)
        )
    )
    repairs = [_map_repair(r) for r in repair_rows]
    walk_ins = await uow.walk_ins.list_by_shop(shop_id)

    scheduling = get_scheduling_runtime()
    appointments = await scheduling.store.list_appointments(shop_id)

    declined_ids: set[UUID] = set()
    try:
        memory = get_memory_runtime()
        for rec in memory.service.list_memories(
            shop_id, category=MemoryCategory.DECLINED_ESTIMATES, limit=500
        ):
            if rec.customer_id and rec.customer_id in customers:
                declined_ids.add(rec.customer_id)
    except Exception:  # noqa: BLE001 — memory is optional/in-memory
        declined_ids = set()

    last_activity = _build_last_activity(
        customers=customers,
        vehicles_by_id=vehicles_by_id,
        repairs=repairs,
        walk_ins=walk_ins,
        appointments=appointments,
        now=datetime.now(timezone.utc),
    )

    return _ShopAudienceContext(
        shop_id=shop_id,
        shop_name=shop_name,
        customers=customers,
        vehicles_by_customer=vehicles_by_customer,
        vehicles_by_id=vehicles_by_id,
        repairs=repairs,
        walk_ins=walk_ins,
        appointments=appointments,
        declined_memory_customer_ids=declined_ids,
        last_activity_by_customer=last_activity,
    )


def _bump_activity(
    acc: dict[UUID, datetime], customer_id: UUID | None, stamp: datetime | None
) -> None:
    if customer_id is None or stamp is None:
        return
    aware = _aware(stamp)
    if aware is None:
        return
    prev = acc.get(customer_id)
    if prev is None or aware > prev:
        acc[customer_id] = aware


def _build_last_activity(
    *,
    customers: dict[UUID, Customer],
    vehicles_by_id: dict[UUID, Vehicle],
    repairs: list[RepairHistory],
    walk_ins: list[Any],
    appointments: list[Appointment],
    now: datetime,
) -> dict[UUID, datetime]:
    """Single-pass activity index used by inactive-customer resolution."""
    acc: dict[UUID, datetime] = {}
    for customer in customers.values():
        _bump_activity(acc, customer.id, customer.created_at)
    for repair in repairs:
        cid = repair.customer_id
        if cid is None:
            vehicle = vehicles_by_id.get(repair.vehicle_id)
            cid = vehicle.customer_id if vehicle else None
        _bump_activity(acc, cid, repair.created_at)
    for visit in walk_ins:
        _bump_activity(acc, getattr(visit, "customer_id", None), getattr(visit, "arrived_at", None))
    for appt in appointments:
        _bump_activity(acc, appt.customer_id, appt.start)
    # Ensure every customer has a stamp (default now if nothing known).
    for cid in customers:
        acc.setdefault(cid, now)
    return acc


def _last_activity(ctx: _ShopAudienceContext, customer_id: UUID) -> datetime:
    if customer_id in ctx.last_activity_by_customer:
        return ctx.last_activity_by_customer[customer_id]
    customer = ctx.customers[customer_id]
    return _aware(customer.created_at) or ctx.now


def _resolve_declined(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    members: list[AudienceMember] = []
    for repair in ctx.repairs:
        if not (_looks_declined(repair.recommendation) or _looks_declined(repair.description)):
            continue
        cid = repair.customer_id
        vehicle = ctx.vehicles_by_id.get(repair.vehicle_id)
        if cid is None and vehicle is not None:
            cid = vehicle.customer_id
        if cid is None or cid not in ctx.customers:
            continue
        members.append(
            _to_member(
                customer=ctx.customers[cid],
                shop_name=ctx.shop_name,
                vehicle=vehicle,
                service=repair.service_type,
                extra={"source": "repair_history", "repair_id": str(repair.id)},
            )
        )
    for cid in ctx.declined_memory_customer_ids:
        customer = ctx.customers.get(cid)
        if customer is None:
            continue
        vehicles = ctx.vehicles_by_customer.get(cid) or []
        members.append(
            _to_member(
                customer=customer,
                shop_name=ctx.shop_name,
                vehicle=vehicles[0] if vehicles else None,
                service="recommended repair",
                extra={"source": "memory"},
            )
        )
    return _dedupe(members)


def _resolve_inactive(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    cutoff = ctx.now - timedelta(days=INACTIVE_DAYS)
    members: list[AudienceMember] = []
    for customer in ctx.customers.values():
        last = _last_activity(ctx, customer.id)
        if last > cutoff:
            continue
        vehicles = ctx.vehicles_by_customer.get(customer.id) or []
        members.append(
            _to_member(
                customer=customer,
                shop_name=ctx.shop_name,
                vehicle=vehicles[0] if vehicles else None,
                service="inspection",
                extra={"days_inactive": (ctx.now - last).days},
            )
        )
    return members


def _resolve_maintenance(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    members: list[AudienceMember] = []
    repairs_by_vehicle: dict[UUID, list[RepairHistory]] = {}
    for repair in ctx.repairs:
        repairs_by_vehicle.setdefault(repair.vehicle_id, []).append(repair)

    for vehicle in ctx.vehicles_by_id.values():
        if not vehicle.customer_id or vehicle.customer_id not in ctx.customers:
            continue
        history = repairs_by_vehicle.get(vehicle.id) or []
        last_by_key: dict[str, datetime] = {}
        for repair in history:
            key = _normalize_service_key(repair.service_type)
            if not key or not repair.created_at:
                continue
            created = _aware(repair.created_at) or ctx.now
            prev = last_by_key.get(key)
            if prev is None or created > prev:
                last_by_key[key] = created

        due_service: str | None = None
        for key, spec in SERVICE_CATALOG.items():
            last = last_by_key.get(key)
            if last is None:
                # No history for this service — skip unless vehicle itself is older than interval
                created = _aware(vehicle.created_at)
                if created and (ctx.now - created).days >= spec.interval_days:
                    due_service = spec.label
                    break
                continue
            if (ctx.now - last).days >= spec.interval_days:
                due_service = spec.label
                break
        if not due_service:
            continue
        members.append(
            _to_member(
                customer=ctx.customers[vehicle.customer_id],
                shop_name=ctx.shop_name,
                vehicle=vehicle,
                service=due_service,
                extra={"source": "maintenance_interval"},
            )
        )
    return _dedupe(members)


def _resolve_thank_you(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    cutoff = ctx.now - timedelta(days=THANK_YOU_DAYS)
    members: list[AudienceMember] = []
    for appt in ctx.appointments:
        if appt.status != AppointmentStatus.COMPLETED.value:
            continue
        start = _aware(appt.start)
        if start is None or start < cutoff or appt.customer_id not in ctx.customers:
            continue
        vehicle = ctx.vehicles_by_id.get(appt.vehicle_id) if appt.vehicle_id else None
        members.append(
            _to_member(
                customer=ctx.customers[appt.customer_id],
                shop_name=ctx.shop_name,
                vehicle=vehicle,
                service=appt.repair_type or "service",
                extra={"appointment_id": str(appt.id)},
            )
        )
    # Also thank recent completed repairs when appointments are sparse
    if not members:
        for repair in ctx.repairs:
            created = _aware(repair.created_at)
            if created is None or created < cutoff:
                continue
            cid = repair.customer_id
            vehicle = ctx.vehicles_by_id.get(repair.vehicle_id)
            if cid is None and vehicle is not None:
                cid = vehicle.customer_id
            if cid is None or cid not in ctx.customers:
                continue
            members.append(
                _to_member(
                    customer=ctx.customers[cid],
                    shop_name=ctx.shop_name,
                    vehicle=vehicle,
                    service=repair.service_type,
                    extra={"repair_id": str(repair.id)},
                )
            )
    return _dedupe(members)


def _resolve_missed(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    cutoff = ctx.now - timedelta(days=MISSED_APPOINTMENT_DAYS)
    members: list[AudienceMember] = []
    for appt in ctx.appointments:
        if appt.status != AppointmentStatus.NO_SHOW.value:
            continue
        start = _aware(appt.start)
        if start is None or start < cutoff or appt.customer_id not in ctx.customers:
            continue
        vehicle = ctx.vehicles_by_id.get(appt.vehicle_id) if appt.vehicle_id else None
        members.append(
            _to_member(
                customer=ctx.customers[appt.customer_id],
                shop_name=ctx.shop_name,
                vehicle=vehicle,
                service=appt.repair_type or "appointment",
                extra={"appointment_id": str(appt.id), "source": "no_show"},
            )
        )
    return _dedupe(members)


def _resolve_default(ctx: _ShopAudienceContext) -> list[AudienceMember]:
    """Fallback: all contactable customers in the shop."""
    members: list[AudienceMember] = []
    for customer in ctx.customers.values():
        if not customer.phone and not customer.email:
            continue
        vehicles = ctx.vehicles_by_customer.get(customer.id) or []
        members.append(
            _to_member(
                customer=customer,
                shop_name=ctx.shop_name,
                vehicle=vehicles[0] if vehicles else None,
                service="service",
            )
        )
    return members


def resolve_from_context(
    ctx: _ShopAudienceContext,
    campaign_type: CampaignType | str,
    *,
    tags: list[str] | None = None,
    segment: str | None = None,
) -> list[AudienceMember]:
    ctype = campaign_type if isinstance(campaign_type, CampaignType) else CampaignType(campaign_type)
    tag_set = set(tags or [])
    resolved_segment = segment or (
        "missed_appointment" if "missed_appointment" in tag_set else None
    )

    if resolved_segment == "missed_appointment":
        return _resolve_missed(ctx)
    if ctype == CampaignType.DECLINED_ESTIMATE:
        return _resolve_declined(ctx)
    if ctype == CampaignType.INACTIVE_CUSTOMER:
        return _resolve_inactive(ctx)
    if ctype == CampaignType.MAINTENANCE_REMINDER:
        return _resolve_maintenance(ctx)
    if ctype == CampaignType.THANK_YOU:
        return _resolve_thank_you(ctx)
    return _resolve_default(ctx)


async def resolve_audience(
    uow: SqlAlchemyUnitOfWork,
    shop_id: UUID,
    campaign_type: CampaignType | str,
    *,
    tags: list[str] | None = None,
    segment: str | None = None,
) -> list[AudienceMember]:
    ctx = await _load_context(uow, shop_id)
    return resolve_from_context(ctx, campaign_type, tags=tags, segment=segment)


async def list_suggested_action_counts(
    uow: SqlAlchemyUnitOfWork,
    shop_id: UUID,
    *,
    exclude_customer_ids: Callable[[str], Awaitable[set[UUID]]] | None = None,
) -> list[SuggestedActionCount]:
    """Build AI recommendation cards.

    exclude_customer_ids: optional async callable (campaign_type) -> customer IDs to
    suppress (recent SMS/email until cooldown elapses).
    """
    ctx = await _load_context(uow, shop_id)
    results: list[SuggestedActionCount] = []
    for action in SUGGESTED_ACTION_DEFS:
        members = resolve_from_context(
            ctx,
            action["campaign_type"],
            tags=[action["id"]],
            segment=action.get("segment"),
        )
        if exclude_customer_ids is not None:
            suppressed: set[UUID] = await exclude_customer_ids(action["campaign_type"])
            if suppressed:
                members = [m for m in members if m.customer_id not in suppressed]
        results.append(
            SuggestedActionCount(
                id=action["id"],
                campaign_type=action["campaign_type"],
                title=action["title"],
                description=action["description"],
                count=len(members),
                custom_message=action.get("custom_message"),
            )
        )
    return results


def audience_to_dicts(members: list[AudienceMember]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in members:
        out.append(
            {
                "customer_id": str(m.customer_id),
                "name": m.name,
                "phone": m.phone,
                "email": m.email,
                "preferred_channel": m.preferred_channel.value if m.preferred_channel else None,
                "metadata": m.metadata,
            }
        )
    return out
