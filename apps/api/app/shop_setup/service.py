"""Shop setup + service catalog business logic."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.models import ShopModel
from app.shop_setup.defaults import (
    BAY_TYPES,
    SERVICE_CATEGORIES,
    SERVICE_SKILLS,
    STARTER_SERVICES,
    WEEKDAY_LABELS,
    default_business_hours,
)
from app.shop_setup.models import ShopBusinessHoursModel, ShopServiceModel, ShopSetupProfileModel
from app.shop_setup.schemas import (
    BusinessHoursIn,
    BusinessHoursOut,
    CompleteSetupRequest,
    PhoneSchedulingCatalogOut,
    ServiceIn,
    ServiceOut,
    ServiceUpdate,
    SetupStateOut,
    SetupStatusOut,
    ShopProfileIn,
    ShopProfileOut,
    UpdateShopSettingsRequest,
)


def _meta() -> dict:
    return {
        "categories": SERVICE_CATEGORIES,
        "skills": SERVICE_SKILLS,
        "bay_types": BAY_TYPES,
        "weekday_labels": WEEKDAY_LABELS,
        "starter_services": [
            {
                "name": s["name"],
                "category": s["category"],
                "duration_minutes": s["duration_minutes"],
                "price": str(s["price"]),
                "skill": s["skill"],
                "bay": s["bay"],
                "active": s["active"],
            }
            for s in STARTER_SERVICES
        ],
        "default_business_hours": default_business_hours(),
    }


def _service_out(row: ShopServiceModel) -> ServiceOut:
    return ServiceOut(
        id=row.id,
        shop_id=row.shop_id,
        name=row.name,
        category=row.category,
        duration_minutes=row.duration_minutes,
        price=Decimal(str(row.price)),
        skill=row.skill,
        bay=row.bay,
        active=row.active,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _hours_out(row: ShopBusinessHoursModel) -> BusinessHoursOut:
    return BusinessHoursOut(
        weekday=row.weekday,
        open_time=row.open_time,
        close_time=row.close_time,
        closed=row.closed,
    )


def _format_address(profile: ShopSetupProfileModel | None) -> str | None:
    if profile is None:
        return None
    parts = [
        profile.address_line1,
        profile.address_line2,
        ", ".join(p for p in [profile.city, profile.state, profile.postal_code] if p),
        profile.country if profile.country and profile.country != "US" else None,
    ]
    text = ", ".join(p for p in parts if p)
    return text or None


class ShopSetupService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _rebind_shop(self, shop_id: UUID) -> None:
        """RLS `app.shop_id` is transaction-local; restore after commit."""
        await self._session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )

    async def _get_shop(self, shop_id: UUID) -> ShopModel:
        shop = await self._session.get(ShopModel, shop_id)
        if shop is None:
            raise NotFoundError("Shop not found")
        return shop

    async def _get_profile(self, shop_id: UUID) -> ShopSetupProfileModel | None:
        return await self._session.get(ShopSetupProfileModel, shop_id)

    async def _get_owner_user(self, shop_id: UUID):
        """Return the shop owner UserModel, if any."""
        from app.domain.enums import UserRole
        from app.infrastructure.models import ShopMembershipModel, UserModel

        result = await self._session.execute(
            select(UserModel)
            .join(ShopMembershipModel, ShopMembershipModel.user_id == UserModel.id)
            .where(
                ShopMembershipModel.shop_id == shop_id,
                ShopMembershipModel.role == UserRole.OWNER.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _owner_contact(self, shop_id: UUID) -> tuple[str | None, str | None]:
        """Owner phone/email from signup — used to prefill shop contact fields."""
        owner = await self._get_owner_user(shop_id)
        if owner is None:
            return None, None
        return owner.phone, owner.email

    async def _sync_owner_contact_from_profile(
        self, shop_id: UUID, profile: ShopSetupProfileModel
    ) -> None:
        """Fill empty owner account email/phone from shop profile.

        Phone signup never collects owner email; users enter it in setup as shop
        contact. Settings reads User.email, so keep the two in sync when the
        account field is still empty.
        """
        from app.auth.otp import normalize_email, normalize_phone
        from app.domain.exceptions import ValidationError as DomainValidationError
        from app.infrastructure.models import UserModel

        owner = await self._get_owner_user(shop_id)
        if owner is None:
            return

        changed = False
        profile_phone = (profile.phone or "").strip() or None
        profile_email = (profile.email or "").strip() or None

        if not (owner.phone or "").strip() and profile_phone:
            try:
                phone = normalize_phone(profile_phone)
            except DomainValidationError:
                phone = None
            if phone:
                other = await self._session.scalar(
                    select(UserModel.id).where(UserModel.phone == phone).limit(1)
                )
                if other is None or other == owner.id:
                    owner.phone = phone
                    owner.phone_verified = True
                    changed = True

        if not (owner.email or "").strip() and profile_email:
            try:
                email = normalize_email(profile_email)
            except DomainValidationError:
                email = None
            if email:
                other = await self._session.scalar(
                    select(UserModel.id).where(UserModel.email == email).limit(1)
                )
                if other is None or other == owner.id:
                    owner.email = email
                    owner.email_verified = True
                    changed = True

        if changed:
            await self._session.flush()

    async def _get_or_create_profile(self, shop_id: UUID) -> ShopSetupProfileModel:
        profile = await self._get_profile(shop_id)
        owner_phone, owner_email = await self._owner_contact(shop_id)
        if profile is None:
            now = datetime.now(timezone.utc)
            profile = ShopSetupProfileModel(
                shop_id=shop_id,
                phone=owner_phone,
                email=owner_email,
                country="US",
                created_at=now,
                updated_at=now,
            )
            self._session.add(profile)
            await self._session.flush()
            return profile
        # Backfill empty shop contact from owner (existing shops registered before seed).
        changed = False
        if not (profile.phone or "").strip() and owner_phone:
            profile.phone = owner_phone
            changed = True
        if not (profile.email or "").strip() and owner_email:
            profile.email = owner_email
            changed = True
        if changed:
            profile.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
        # Reverse: phone signup leaves User.email empty; heal from shop profile.
        await self._sync_owner_contact_from_profile(shop_id, profile)
        return profile

    def _empty_profile(self, shop_id: UUID) -> ShopSetupProfileModel:
        now = datetime.now(timezone.utc)
        return ShopSetupProfileModel(
            shop_id=shop_id,
            country="US",
            created_at=now,
            updated_at=now,
        )

    async def _list_hours(self, shop_id: UUID) -> list[ShopBusinessHoursModel]:
        result = await self._session.execute(
            select(ShopBusinessHoursModel)
            .where(ShopBusinessHoursModel.shop_id == shop_id)
            .order_by(ShopBusinessHoursModel.weekday)
        )
        return list(result.scalars().all())

    async def _list_services(
        self, shop_id: UUID, *, active_only: bool = False
    ) -> list[ShopServiceModel]:
        stmt = (
            select(ShopServiceModel)
            .where(ShopServiceModel.shop_id == shop_id)
            .order_by(ShopServiceModel.sort_order, ShopServiceModel.name)
        )
        if active_only:
            stmt = stmt.where(ShopServiceModel.active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _profile_out(self, shop: ShopModel, profile: ShopSetupProfileModel) -> ShopProfileOut:
        return ShopProfileOut(
            shop_id=shop.id,
            name=shop.name,
            slug=shop.slug,
            timezone=shop.timezone,
            phone=profile.phone,
            email=profile.email,
            address_line1=profile.address_line1,
            address_line2=profile.address_line2,
            city=profile.city,
            state=profile.state,
            postal_code=profile.postal_code,
            country=profile.country or "US",
            website=profile.website,
            description=profile.description,
            setup_completed=profile.setup_completed_at is not None,
            setup_completed_at=profile.setup_completed_at,
        )

    def _validate_hours(self, hours: list[BusinessHoursIn]) -> None:
        if len(hours) != 7:
            raise ValidationError("Business hours must include all 7 weekdays")
        weekdays = sorted(h.weekday for h in hours)
        if weekdays != list(range(7)):
            raise ValidationError("Business hours must cover weekdays 0–6 exactly once")
        # All-closed is allowed (temporary closure / holiday). Only validate open days.
        for h in hours:
            if h.closed:
                continue
            if h.open_time >= h.close_time:
                raise ValidationError(
                    f"Open time must be before close time for weekday {h.weekday}"
                )

    def _has_shop_info(self, shop: ShopModel, profile: ShopSetupProfileModel) -> bool:
        has_contact = bool((profile.phone or "").strip() or (profile.email or "").strip())
        return bool(shop.name.strip()) and has_contact

    def _build_status(
        self,
        shop: ShopModel,
        profile: ShopSetupProfileModel,
        hours: list[ShopBusinessHoursModel],
        services: list[ShopServiceModel],
    ) -> SetupStatusOut:
        has_shop_info = self._has_shop_info(shop, profile)
        # Hours are configured once 7 weekday rows exist (all-closed is still configured).
        has_hours = len(hours) == 7
        active_services = [s for s in services if s.active]
        has_services = len(active_services) >= 1
        missing: list[str] = []
        if not has_shop_info:
            missing.append("shop_info")
        if not has_hours:
            missing.append("business_hours")
        if not has_services:
            missing.append("services")
        completed = profile.setup_completed_at is not None and not missing
        return SetupStatusOut(
            setup_completed=completed,
            has_shop_info=has_shop_info,
            has_business_hours=has_hours,
            has_services=has_services,
            service_count=len(services),
            missing=missing,
        )

    async def get_status(self, shop_id: UUID) -> SetupStatusOut:
        shop = await self._get_shop(shop_id)
        profile = await self._get_or_create_profile(shop_id)
        await self._session.commit()
        await self._rebind_shop(shop_id)
        hours = await self._list_hours(shop_id)
        services = await self._list_services(shop_id)
        return self._build_status(shop, profile, hours, services)

    async def get_state(self, shop_id: UUID) -> SetupStateOut:
        shop = await self._get_shop(shop_id)
        profile = await self._get_or_create_profile(shop_id)
        await self._session.commit()
        await self._rebind_shop(shop_id)
        hours_rows = await self._list_hours(shop_id)
        services = await self._list_services(shop_id)
        hours_out = [_hours_out(h) for h in hours_rows]
        if len(hours_out) != 7:
            hours_out = [BusinessHoursOut(**h) for h in default_business_hours()]
        status = self._build_status(shop, profile, hours_rows, services)
        return SetupStateOut(
            status=status,
            profile=self._profile_out(shop, profile),
            business_hours=hours_out,
            services=[_service_out(s) for s in services],
            meta=_meta(),
        )

    async def _apply_profile(self, shop: ShopModel, profile: ShopSetupProfileModel, data: ShopProfileIn) -> None:
        patch = data.model_dump(exclude_unset=True)
        if "name" in patch and patch["name"] is not None:
            name = patch["name"].strip()
            if len(name) < 2:
                raise ValidationError("Shop name too short")
            shop.name = name
            # Keep internal slug aligned with display name so login-by-name works.
            from app.domain.slug import next_slug_candidate, slugify_shop_name
            from app.infrastructure.models import ShopModel as _Shop

            base = slugify_shop_name(name)
            for attempt in range(1, 50):
                candidate = next_slug_candidate(base, attempt)
                existing = await self._session.scalar(
                    select(_Shop.id).where(_Shop.slug == candidate, _Shop.id != shop.id)
                )
                if existing is None:
                    shop.slug = candidate
                    break
            else:
                shop.slug = f"shop-{uuid4().hex[:8]}"
        if "timezone" in patch and patch["timezone"] is not None:
            tz = patch["timezone"].strip()
            if not tz:
                raise ValidationError("Invalid timezone")
            shop.timezone = tz
        for field in (
            "phone",
            "email",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "website",
            "description",
        ):
            if field in patch:
                value = patch[field]
                if isinstance(value, str):
                    value = value.strip() or None
                setattr(profile, field, value)
        profile.updated_at = datetime.now(timezone.utc)

    async def _replace_hours(self, shop_id: UUID, hours: list[BusinessHoursIn]) -> None:
        self._validate_hours(hours)
        await self._session.execute(
            delete(ShopBusinessHoursModel).where(ShopBusinessHoursModel.shop_id == shop_id)
        )
        for h in sorted(hours, key=lambda x: x.weekday):
            self._session.add(
                ShopBusinessHoursModel(
                    id=uuid4(),
                    shop_id=shop_id,
                    weekday=h.weekday,
                    open_time=h.open_time,
                    close_time=h.close_time,
                    closed=bool(h.closed),
                )
            )
        await self._session.flush()

    async def _replace_services(self, shop_id: UUID, services: list[ServiceIn]) -> list[ShopServiceModel]:
        if not services:
            raise ValidationError("At least one service is required")
        await self._session.execute(
            delete(ShopServiceModel).where(ShopServiceModel.shop_id == shop_id)
        )
        rows: list[ShopServiceModel] = []
        now = datetime.now(timezone.utc)
        for idx, svc in enumerate(services):
            row = ShopServiceModel(
                id=uuid4(),
                shop_id=shop_id,
                name=svc.name.strip(),
                category=svc.category.strip().lower(),
                duration_minutes=svc.duration_minutes,
                price=svc.price,
                skill=svc.skill.strip().lower(),
                bay=svc.bay.strip().lower(),
                active=svc.active,
                sort_order=svc.sort_order if svc.sort_order is not None else idx,
                created_at=now,
                updated_at=now,
            )
            if not row.name:
                raise ValidationError("Service name is required")
            self._session.add(row)
            rows.append(row)
        if not any(r.active for r in rows):
            raise ValidationError("At least one active service is required")
        await self._session.flush()
        return rows

    async def complete_setup(self, shop_id: UUID, body: CompleteSetupRequest) -> SetupStateOut:
        shop = await self._get_shop(shop_id)
        profile = await self._get_or_create_profile(shop_id)
        await self._apply_profile(shop, profile, body.profile)
        await self._sync_owner_contact_from_profile(shop_id, profile)
        await self._replace_hours(shop_id, body.business_hours)
        await self._replace_services(shop_id, body.services)
        if not self._has_shop_info(shop, profile):
            raise ValidationError(
                "Shop info requires a name plus phone/email or street address and city"
            )
        profile.setup_completed_at = datetime.now(timezone.utc)
        profile.updated_at = profile.setup_completed_at
        await self._session.commit()
        await self._rebind_shop(shop_id)
        return await self.get_state(shop_id)

    async def update_settings(self, shop_id: UUID, body: UpdateShopSettingsRequest) -> SetupStateOut:
        if body.profile is None and body.business_hours is None:
            raise ValidationError("No changes provided")
        shop = await self._get_shop(shop_id)
        profile = await self._get_or_create_profile(shop_id)
        if body.profile is not None:
            await self._apply_profile(shop, profile, body.profile)
            await self._sync_owner_contact_from_profile(shop_id, profile)
        if body.business_hours is not None:
            await self._replace_hours(shop_id, body.business_hours)
        await self._session.commit()
        await self._rebind_shop(shop_id)
        return await self.get_state(shop_id)

    async def list_services(self, shop_id: UUID, *, active_only: bool = False) -> list[ServiceOut]:
        await self._rebind_shop(shop_id)
        rows = await self._list_services(shop_id, active_only=active_only)
        return [_service_out(r) for r in rows]

    async def get_service(self, shop_id: UUID, service_id: UUID) -> ServiceOut:
        row = await self._session.get(ShopServiceModel, service_id)
        if row is None or row.shop_id != shop_id:
            raise NotFoundError("Service not found")
        return _service_out(row)

    async def _assert_unique_service_name(
        self,
        shop_id: UUID,
        name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        normalized = name.strip().lower()
        if not normalized:
            return
        existing = await self._list_services(shop_id)
        for row in existing:
            if exclude_id is not None and row.id == exclude_id:
                continue
            if row.name.strip().lower() == normalized:
                raise ConflictError("A service with this name already exists")

    async def create_service(self, shop_id: UUID, body: ServiceIn) -> ServiceOut:
        await self._get_shop(shop_id)
        now = datetime.now(timezone.utc)
        existing = await self._list_services(shop_id)
        sort_order = body.sort_order if body.sort_order is not None else len(existing)
        name = body.name.strip()
        if not name:
            raise ValidationError("Service name is required")
        await self._assert_unique_service_name(shop_id, name)
        row = ShopServiceModel(
            id=uuid4(),
            shop_id=shop_id,
            name=name,
            category=body.category.strip().lower(),
            duration_minutes=body.duration_minutes,
            price=body.price,
            skill=body.skill.strip().lower(),
            bay=body.bay.strip().lower(),
            active=body.active,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        await self._rebind_shop(shop_id)
        await self._session.refresh(row)
        return _service_out(row)

    async def update_service(self, shop_id: UUID, service_id: UUID, body: ServiceUpdate) -> ServiceOut:
        row = await self._session.get(ShopServiceModel, service_id)
        if row is None or row.shop_id != shop_id:
            raise NotFoundError("Service not found")
        patch = body.model_dump(exclude_unset=True)
        if not patch:
            raise ValidationError("No changes provided")
        for key, value in patch.items():
            if key in {"name", "category", "skill", "bay"} and isinstance(value, str):
                value = value.strip()
                if key != "name":
                    value = value.lower()
                if not value:
                    raise ValidationError(f"{key} is required")
            if key == "name" and isinstance(value, str):
                await self._assert_unique_service_name(shop_id, value, exclude_id=service_id)
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._rebind_shop(shop_id)
        await self._session.refresh(row)
        return _service_out(row)

    async def delete_service(self, shop_id: UUID, service_id: UUID) -> None:
        row = await self._session.get(ShopServiceModel, service_id)
        if row is None or row.shop_id != shop_id:
            raise NotFoundError("Service not found")
        remaining = await self._list_services(shop_id)
        profile = await self._get_profile(shop_id)
        if profile is not None and profile.setup_completed_at is not None:
            active_others = [s for s in remaining if s.id != service_id and s.active]
            if not active_others:
                raise ValidationError("At least one active service is required after setup")
        await self._session.delete(row)
        await self._session.commit()

    async def phone_scheduling_catalog(self, shop_id: UUID) -> PhoneSchedulingCatalogOut:
        shop = await self._get_shop(shop_id)
        profile = await self._get_profile(shop_id) or self._empty_profile(shop_id)
        hours = await self._list_hours(shop_id)
        services = await self._list_services(shop_id, active_only=True)
        hours_out = [_hours_out(h) for h in hours]
        if len(hours_out) != 7:
            hours_out = [BusinessHoursOut(**h) for h in default_business_hours()]
        return PhoneSchedulingCatalogOut(
            shop_id=shop.id,
            shop_name=shop.name,
            shop_slug=shop.slug,
            timezone=shop.timezone,
            phone=profile.phone,
            address=_format_address(profile),
            business_hours=hours_out,
            services=[_service_out(s) for s in services],
            bookable_service_count=len(services),
        )
