"""Service Catalog bridge for appointment booking.

Keeps scheduling engines unchanged while resolving duration, hours,
and service_id from the shop catalog (dashboard + AI Decision Layer).

Also syncs Team roster → mechanics and catalog bay types → bay resources
so Schedule reflects live shop configuration instead of seed data.

AI name-matching lives in ``app.agents.scheduling.catalog_match`` (read-only).
Workflow creates appointments — AI never writes the database.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import NotFoundError, ValidationError
from app.infrastructure.models import ShopMembershipModel, UserModel
from app.scheduling.models import Bay, BookingRequest, BusinessHours, Mechanic, MechanicSkill
from app.scheduling.store import InMemoryShopResourceStore, ShopResourcePort
from app.shop_setup.schemas import ServiceOut
from app.shop_setup.service import ShopSetupService


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid time: {value}")
    return time(int(parts[0]), int(parts[1]))


def _stable_bay_id(shop_id: UUID, bay_type: str, index: int = 0) -> UUID:
    return uuid5(NAMESPACE_URL, f"shop:{shop_id}:bay:{bay_type}:{index}")


async def resolve_bookable_service(
    session: AsyncSession,
    *,
    shop_id: UUID,
    service_id: UUID,
) -> ServiceOut:
    """Load an active catalog service for booking."""
    svc = ShopSetupService(session)
    service = await svc.get_service(shop_id, service_id)
    if not service.active:
        raise ValidationError("Selected service is not active")
    return service


async def sync_catalog_hours(
    session: AsyncSession,
    *,
    shop_id: UUID,
    store: ShopResourcePort,
) -> tuple[list[int], time, time]:
    """Apply shop-setup business hours to the scheduling store when possible.

    Returns (open weekdays, work_start, work_end) for mechanic sync.
    work_start/end are the envelope across open days so staff cover all
    shop hours; per-day open/close still gates booking via business hours.
    """
    default_start, default_end = time(8, 0), time(17, 0)
    if not isinstance(store, InMemoryShopResourceStore):
        return list(range(5)), default_start, default_end
    setup = ShopSetupService(session)
    state = await setup.get_state(shop_id)
    hours = [
        BusinessHours(
            weekday=h.weekday,
            open_time=_parse_hhmm(h.open_time),
            close_time=_parse_hhmm(h.close_time),
            closed=h.closed,
        )
        for h in state.business_hours
    ]
    if hours:
        store.set_business_hours(shop_id, hours)
        open_days = [h for h in hours if not h.closed]
        if open_days:
            return (
                [h.weekday for h in open_days],
                min(h.open_time for h in open_days),
                max(h.close_time for h in open_days),
            )
    return list(range(5)), default_start, default_end


_ALL_VEHICLE_TYPES = ["sedan", "suv", "truck", "van", "ev", "other"]


async def sync_catalog_bays(
    session: AsyncSession,
    *,
    shop_id: UUID,
    store: ShopResourcePort,
) -> None:
    """Build one physical bay lane per Team member.

    Catalog bay types are labels for preference scoring only — parallel intake
    must equal Team size, not distinct service.bay values.
    """
    if not isinstance(store, InMemoryShopResourceStore):
        return
    setup = ShopSetupService(session)
    services = await setup.list_services(shop_id, active_only=True)
    bay_types: list[str] = []
    seen: set[str] = set()
    for svc in services:
        bay_type = (svc.bay or "general").strip().lower() or "general"
        if bay_type in seen:
            continue
        seen.add(bay_type)
        bay_types.append(bay_type)
    if not bay_types:
        bay_types = ["general"]
    mechanics = await store.list_mechanics(shop_id)
    capacity = max(1, len(mechanics))
    # One lane per staff; rotate catalog labels for display/preference only.
    bays = [
        Bay(
            id=_stable_bay_id(shop_id, "lane", index),
            shop_id=shop_id,
            name=f"Bay {index + 1}",
            bay_type=bay_types[index % len(bay_types)],
            supports_vehicle_types=list(_ALL_VEHICLE_TYPES),
        )
        for index in range(capacity)
    ]
    store.set_bays(shop_id, bays)


async def sync_team_mechanics(
    session: AsyncSession,
    *,
    shop_id: UUID,
    store: ShopResourcePort,
    workdays: list[int] | None = None,
    work_start: time | None = None,
    work_end: time | None = None,
) -> None:
    """Map Team roster (owner + staff) into scheduling mechanics."""
    if not isinstance(store, InMemoryShopResourceStore):
        return

    # Explicit JOIN so staff rows are never dropped when the user relationship
    # fails to lazy/selectin-load under a short-lived request session.
    result = await session.execute(
        select(ShopMembershipModel, UserModel)
        .join(UserModel, UserModel.id == ShopMembershipModel.user_id)
        .where(ShopMembershipModel.shop_id == shop_id)
        .where(UserModel.is_active.is_(True))
        .order_by(ShopMembershipModel.created_at.asc())
    )
    rows = list(result.all())
    if not rows:
        return

    setup = ShopSetupService(session)
    services = await setup.list_services(shop_id, active_only=True)
    skill_types = sorted(
        {(svc.skill or "general").strip().lower() or "general" for svc in services}
    )
    if not skill_types:
        skill_types = ["general"]
    skills = [MechanicSkill(repair_type=s, proficiency=4) for s in skill_types]
    mechanic_workdays = workdays if workdays is not None else list(range(5))
    if not mechanic_workdays:
        mechanic_workdays = list(range(5))
    mechanic_start = work_start or time(8, 0)
    mechanic_end = work_end or time(17, 0)

    # Entire active roster = parallel intake capacity (Team size).
    candidates: list[Mechanic] = []
    seen: set[UUID] = set()
    for membership, user in rows:
        role = (membership.role or "staff").strip().lower() or "staff"
        if role == "ai_agent":
            continue
        if user.id in seen:
            continue
        seen.add(user.id)
        candidates.append(
            Mechanic(
                id=user.id,
                shop_id=shop_id,
                name=user.full_name or "Team member",
                skills=list(skills),
                work_start=mechanic_start,
                work_end=mechanic_end,
                workdays=list(mechanic_workdays),
                role=role,
            )
        )

    if candidates:
        # Seed/default mechanics use ephemeral ids. SMS/voice may book against
        # those before the Schedule page syncs Team — remap so appointments
        # remain visible under Team columns.
        previous = {m.id: m for m in await store.list_mechanics(shop_id)}
        store.set_mechanics(shop_id, candidates)
        await _remap_orphan_appointment_mechanics(
            store,
            shop_id=shop_id,
            previous=previous,
            team=candidates,
        )


async def _remap_orphan_appointment_mechanics(
    store: InMemoryShopResourceStore,
    *,
    shop_id: UUID,
    previous: dict[UUID, Mechanic],
    team: list[Mechanic],
) -> None:
    """Point appointments at Team ids when seed/stale mechanic ids were replaced."""
    if not team:
        return
    valid = {m.id for m in team}
    by_name = {m.name.strip().lower(): m.id for m in team if m.name}
    fallback = team[0].id
    for appt_id in list(store._by_shop.get(shop_id, [])):  # noqa: SLF001
        appt = store.appointments.get(appt_id)
        if appt is None or appt.mechanic_id is None or appt.mechanic_id in valid:
            continue
        old = previous.get(appt.mechanic_id)
        if old is not None:
            mapped = by_name.get((old.name or "").strip().lower())
            appt.mechanic_id = mapped or fallback
        else:
            appt.mechanic_id = fallback
        await store.update_appointment(appt)


async def ensure_shop_resources_synced(shop_id: UUID, store: ShopResourcePort) -> None:
    """Best-effort Team/catalog sync for SMS/voice/agent paths (no HTTP session).

    Schedule UI syncs on calendar load; agent bookings must sync first so
    appointments land on real Team mechanic ids (not seed defaults).
    """
    if not isinstance(store, InMemoryShopResourceStore):
        return
    try:
        from sqlalchemy import text

        from app.infrastructure.database import SessionLocal

        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            await sync_shop_resources(session, shop_id=shop_id, store=store)
    except Exception:  # noqa: BLE001 — tests / offline keep seed shop
        store.ensure_shop(shop_id)


async def sync_shop_resources(
    session: AsyncSession,
    *,
    shop_id: UUID,
    store: ShopResourcePort,
) -> None:
    """Sync hours, Team mechanics, and catalog bays into the scheduling store."""
    open_weekdays, work_start, work_end = await sync_catalog_hours(
        session, shop_id=shop_id, store=store
    )
    await sync_team_mechanics(
        session,
        shop_id=shop_id,
        store=store,
        workdays=open_weekdays,
        work_start=work_start,
        work_end=work_end,
    )
    await sync_catalog_bays(session, shop_id=shop_id, store=store)


def build_booking_request(
    *,
    shop_id: UUID,
    service: ServiceOut,
    preferred_start=None,
    customer_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    vehicle_type: str = "sedan",
    priority: str = "normal",
    notes: str | None = None,
    walk_in_id: UUID | None = None,
    mechanic_id: UUID | None = None,
    bay_id: UUID | None = None,
    estimated_revenue: Decimal | None = None,
    source: str = "dashboard",
) -> BookingRequest:
    """Map catalog service → booking fields (duration drives end time)."""
    return BookingRequest(
        shop_id=shop_id,
        preferred_start=preferred_start,
        customer_id=customer_id,
        vehicle_id=vehicle_id,
        service_id=service.id,
        repair_type=(service.skill or "general").strip().lower() or "general",
        required_bay=(service.bay or "general").strip().lower() or "general",
        vehicle_type=vehicle_type,
        priority=priority,
        estimated_duration_min=service.duration_minutes,
        source=source,
        notes=notes,
        walk_in_id=walk_in_id,
        mechanic_id=mechanic_id,
        bay_id=bay_id,
        estimated_revenue=estimated_revenue
        if estimated_revenue is not None
        else Decimal(str(service.price)),
        service_name=service.name,
    )


async def require_service_for_booking(
    session: AsyncSession,
    *,
    shop_id: UUID,
    service_id: UUID | None,
    store: ShopResourcePort,
) -> ServiceOut:
    if service_id is None:
        raise ValidationError("service_id is required to book an appointment")
    try:
        service = await resolve_bookable_service(
            session, shop_id=shop_id, service_id=service_id
        )
    except NotFoundError as exc:
        raise ValidationError(str(exc)) from exc
    await sync_shop_resources(session, shop_id=shop_id, store=store)
    return service
