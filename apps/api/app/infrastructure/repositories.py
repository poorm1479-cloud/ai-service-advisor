from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    CommunicationHistory,
    Customer,
    RefreshToken,
    RepairHistory,
    Shop,
    ShopMembership,
    User,
    Vehicle,
    VoiceNote,
    WalkInVisit,
)
from app.domain.enums import CommunicationChannel, CommunicationDirection, UserRole, WalkInStatus
from app.infrastructure.models import (
    CommunicationHistoryModel,
    CustomerModel,
    RefreshTokenModel,
    RepairHistoryModel,
    ShopMembershipModel,
    ShopModel,
    UserModel,
    VehicleModel,
    VoiceNoteModel,
    WalkInVisitModel,
)


def _shop(m: ShopModel) -> Shop:
    return Shop(id=m.id, name=m.name, slug=m.slug, timezone=m.timezone, created_at=m.created_at)


def _user(m: UserModel) -> User:
    return User(
        id=m.id,
        username=getattr(m, "username", None),
        phone=m.phone,
        email=m.email,
        full_name=m.full_name,
        password_hash=m.password_hash,
        phone_verified=bool(getattr(m, "phone_verified", False)),
        email_verified=bool(getattr(m, "email_verified", False)),
        primary_auth_method=getattr(m, "primary_auth_method", None) or "phone",
        account_type=getattr(m, "account_type", None) or "shop",
        mfa_enabled=bool(getattr(m, "mfa_enabled", False)),
        mfa_secret=getattr(m, "mfa_secret", None),
        mfa_backup_codes_json=getattr(m, "mfa_backup_codes_json", None),
        is_active=m.is_active,
        created_at=m.created_at,
    )


def _membership(m: ShopMembershipModel) -> ShopMembership:
    import json

    from app.domain.enums import normalize_user_role

    caps: list[str] | None = None
    raw = getattr(m, "capabilities_json", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                caps = [str(x) for x in parsed]
        except (TypeError, ValueError, json.JSONDecodeError):
            caps = None
    return ShopMembership(
        id=m.id,
        shop_id=m.shop_id,
        user_id=m.user_id,
        role=normalize_user_role(m.role),
        capabilities=caps,
        created_at=m.created_at,
    )


def _refresh(m: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=m.id,
        user_id=m.user_id,
        shop_id=m.shop_id,
        token_hash=m.token_hash,
        expires_at=m.expires_at,
        revoked_at=m.revoked_at,
        created_at=m.created_at,
    )


def _customer(m: CustomerModel) -> Customer:
    return Customer(
        id=m.id,
        shop_id=m.shop_id,
        name=m.name,
        phone=m.phone,
        email=m.email,
        address=m.address,
        created_at=m.created_at,
    )


def _vehicle(m: VehicleModel) -> Vehicle:
    return Vehicle(
        id=m.id,
        shop_id=m.shop_id,
        customer_id=m.customer_id,
        vin=m.vin,
        license_plate=m.license_plate,
        year=m.year,
        make=m.make,
        model=m.model,
        mileage=m.mileage,
        created_at=m.created_at,
    )


def _repair(m: RepairHistoryModel) -> RepairHistory:
    return RepairHistory(
        id=m.id,
        shop_id=m.shop_id,
        customer_id=m.customer_id,
        vehicle_id=m.vehicle_id,
        service_type=m.service_type,
        description=m.description,
        cost=m.cost,
        recommendation=m.recommendation,
        created_at=m.created_at,
    )


def _communication(m: CommunicationHistoryModel) -> CommunicationHistory:
    return CommunicationHistory(
        id=m.id,
        shop_id=m.shop_id,
        customer_id=m.customer_id,
        channel=CommunicationChannel(m.channel),
        message=m.message,
        direction=CommunicationDirection(m.direction),
        created_at=m.created_at,
    )


def _walk_in(m: WalkInVisitModel) -> WalkInVisit:
    return WalkInVisit(
        id=m.id,
        shop_id=m.shop_id,
        vehicle_id=m.vehicle_id,
        customer_id=m.customer_id,
        complaint=m.complaint,
        status=WalkInStatus(m.status),
        arrived_at=m.arrived_at,
        created_at=m.created_at,
    )


def _voice_note(m: VoiceNoteModel) -> VoiceNote:
    return VoiceNote(
        id=m.id,
        shop_id=m.shop_id,
        employee_id=m.employee_id,
        audio_url=m.audio_url,
        transcript=m.transcript,
        created_at=m.created_at,
    )


class SqlAlchemyShopRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, shop_id: UUID) -> Shop | None:
        row = await self._session.get(ShopModel, shop_id)
        return _shop(row) if row else None

    async def get_by_slug(self, slug: str) -> Shop | None:
        row = await self._session.scalar(select(ShopModel).where(ShopModel.slug == slug))
        return _shop(row) if row else None

    async def add(self, shop: Shop) -> Shop:
        model = ShopModel(id=shop.id, name=shop.name, slug=shop.slug, timezone=shop.timezone)
        self._session.add(model)
        await self._session.flush()
        return _shop(model)

    async def update(self, shop: Shop) -> Shop:
        row = await self._session.get(ShopModel, shop.id)
        if row is None:
            raise ValueError("Shop not found")
        row.name = shop.name
        row.timezone = shop.timezone
        await self._session.flush()
        return _shop(row)


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return _user(row) if row else None

    async def get_by_username(self, username: str) -> User | None:
        row = await self._session.scalar(
            select(UserModel).where(UserModel.username == username.lower())
        )
        return _user(row) if row else None

    async def get_by_phone(self, phone: str) -> User | None:
        row = await self._session.scalar(select(UserModel).where(UserModel.phone == phone))
        return _user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        row = await self._session.scalar(
            select(UserModel).where(UserModel.email == email.lower())
        )
        return _user(row) if row else None

    async def add(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            username=user.username.lower() if user.username else None,
            phone=user.phone,
            email=user.email.lower() if user.email else None,
            full_name=user.full_name,
            password_hash=user.password_hash,
            phone_verified=bool(user.phone_verified),
            email_verified=bool(user.email_verified),
            primary_auth_method=user.primary_auth_method or "phone",
            account_type=(user.account_type or "shop").strip().lower() or "shop",
            mfa_enabled=bool(user.mfa_enabled),
            mfa_secret=user.mfa_secret,
            mfa_backup_codes_json=user.mfa_backup_codes_json,
            is_active=user.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        return _user(model)

    async def update_account_type(self, user_id: UUID, *, account_type: str) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.account_type = (account_type or "shop").strip().lower() or "shop"
        await self._session.flush()
        return _user(row)

    async def update_profile(
        self,
        user_id: UUID,
        *,
        full_name: str,
        phone: str | None | object = ...,
        email: str | None | object = ...,
    ) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.full_name = full_name
        if phone is not ...:
            next_phone = phone if isinstance(phone, str) and phone else None
            if (row.phone or None) != next_phone:
                row.phone = next_phone
                # Authenticated profile update: contact is usable for login.
                # (No separate OTP path for settings contact changes.)
                row.phone_verified = bool(next_phone)
        if email is not ...:
            next_email = email.lower() if isinstance(email, str) and email else None
            if (row.email or None) != next_email:
                row.email = next_email
                row.email_verified = bool(next_email)
        await self._session.flush()
        return _user(row)

    async def update_password(self, user_id: UUID, *, password_hash: str) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.password_hash = password_hash
        await self._session.flush()
        return _user(row)

    async def set_active(self, user_id: UUID, *, is_active: bool) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.is_active = bool(is_active)
        await self._session.flush()
        return _user(row)

    async def get_notification_prefs(self, user_id: UUID) -> dict | None:
        import json

        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        raw = getattr(row, "notification_prefs_json", None)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}

    async def set_notification_prefs(self, user_id: UUID, prefs: dict) -> dict | None:
        import json

        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.notification_prefs_json = json.dumps(prefs)
        await self._session.flush()
        return prefs

    async def set_email_verified(self, user_id: UUID, verified: bool = True) -> None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return
        row.email_verified = verified
        await self._session.flush()

    async def set_phone_verified(self, user_id: UUID, verified: bool = True) -> None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return
        row.phone_verified = verified
        await self._session.flush()

    async def set_mfa(
        self,
        user_id: UUID,
        *,
        secret: str | None,
        enabled: bool,
        backup_codes_json: str | None | object = ...,
    ) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.mfa_secret = secret
        row.mfa_enabled = enabled
        if backup_codes_json is not ...:
            row.mfa_backup_codes_json = backup_codes_json  # type: ignore[assignment]
        await self._session.flush()
        return _user(row)

    async def set_mfa_backup_codes(self, user_id: UUID, backup_codes_json: str | None) -> User | None:
        row = await self._session.get(UserModel, user_id)
        if row is None:
            return None
        row.mfa_backup_codes_json = backup_codes_json
        await self._session.flush()
        return _user(row)


class SqlAlchemyMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, shop_id: UUID, user_id: UUID) -> ShopMembership | None:
        row = await self._session.scalar(
            select(ShopMembershipModel).where(
                ShopMembershipModel.shop_id == shop_id,
                ShopMembershipModel.user_id == user_id,
            )
        )
        return _membership(row) if row else None

    async def add(self, membership: ShopMembership) -> ShopMembership:
        import json

        from app.core.permissions.user_capabilities import default_capabilities_for_role
        from app.domain.enums import normalize_user_role

        role = normalize_user_role(membership.role)
        caps = membership.capabilities
        if caps is None:
            caps = default_capabilities_for_role(role)
        model = ShopMembershipModel(
            id=membership.id,
            shop_id=membership.shop_id,
            user_id=membership.user_id,
            role=role.value,
            capabilities_json=json.dumps(caps),
        )
        self._session.add(model)
        await self._session.flush()
        return _membership(model)

    async def update(self, membership: ShopMembership) -> ShopMembership:
        import json

        from app.domain.enums import normalize_user_role

        row = await self._session.scalar(
            select(ShopMembershipModel).where(ShopMembershipModel.id == membership.id)
        )
        if row is None:
            raise LookupError(f"Membership not found: {membership.id}")
        row.role = normalize_user_role(membership.role).value
        if membership.capabilities is not None:
            row.capabilities_json = json.dumps(list(membership.capabilities))
        await self._session.flush()
        return _membership(row)

    async def delete(self, membership_id: UUID) -> bool:
        result = await self._session.execute(
            delete(ShopMembershipModel).where(ShopMembershipModel.id == membership_id)
        )
        await self._session.flush()
        return bool(result.rowcount)

    async def list_for_user(self, user_id: UUID) -> list[ShopMembership]:
        rows = await self._session.scalars(
            select(ShopMembershipModel).where(ShopMembershipModel.user_id == user_id)
        )
        return [_membership(r) for r in rows]

    async def list_for_shop(self, shop_id: UUID) -> list[ShopMembership]:
        rows = await self._session.scalars(
            select(ShopMembershipModel).where(ShopMembershipModel.shop_id == shop_id)
        )
        return [_membership(r) for r in rows]


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            shop_id=token.shop_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            revoked_at=token.revoked_at,
        )
        self._session.add(model)
        await self._session.flush()
        return _refresh(model)

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        row = await self._session.scalar(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        return _refresh(row) if row else None

    async def revoke(self, token_id: UUID, revoked_at: datetime) -> bool:
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.id == token_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return bool(result.rowcount)

    async def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> None:
        await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

    async def exists_for_user_shop(self, user_id: UUID, shop_id: UUID) -> bool:
        row = await self._session.scalar(
            select(RefreshTokenModel.id)
            .where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.shop_id == shop_id,
            )
            .limit(1)
        )
        return row is not None


class SqlAlchemyCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, customer: Customer) -> Customer:
        model = CustomerModel(
            id=customer.id,
            shop_id=customer.shop_id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _customer(model)

    async def update(self, customer: Customer) -> Customer:
        model = await self._session.scalar(
            select(CustomerModel).where(
                CustomerModel.id == customer.id,
                CustomerModel.shop_id == customer.shop_id,
            )
        )
        if model is None:
            raise ValueError("Customer not found")
        model.name = customer.name
        model.phone = customer.phone
        model.email = customer.email
        model.address = customer.address
        await self._session.flush()
        await self._session.refresh(model)
        return _customer(model)

    async def list_by_shop(self, shop_id: UUID) -> list[Customer]:
        rows = await self._session.scalars(
            select(CustomerModel)
            .where(CustomerModel.shop_id == shop_id)
            .order_by(CustomerModel.created_at.desc())
        )
        return [_customer(r) for r in rows]

    async def search(self, shop_id: UUID, query: str) -> list[Customer]:
        pattern = f"%{query.strip()}%"
        rows = await self._session.scalars(
            select(CustomerModel)
            .where(
                CustomerModel.shop_id == shop_id,
                or_(
                    CustomerModel.name.ilike(pattern),
                    CustomerModel.phone.ilike(pattern),
                    CustomerModel.email.ilike(pattern),
                    CustomerModel.address.ilike(pattern),
                ),
            )
            .order_by(CustomerModel.name.asc())
            .limit(100)
        )
        return [_customer(r) for r in rows]

    async def get_by_id(self, shop_id: UUID, customer_id: UUID) -> Customer | None:
        row = await self._session.scalar(
            select(CustomerModel).where(
                CustomerModel.id == customer_id,
                CustomerModel.shop_id == shop_id,
            )
        )
        return _customer(row) if row else None


class SqlAlchemyVehicleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, vehicle: Vehicle) -> Vehicle:
        model = VehicleModel(
            id=vehicle.id,
            shop_id=vehicle.shop_id,
            customer_id=vehicle.customer_id,
            vin=vehicle.vin,
            license_plate=vehicle.license_plate,
            year=vehicle.year,
            make=vehicle.make,
            model=vehicle.model,
            mileage=vehicle.mileage,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _vehicle(model)

    async def update(self, vehicle: Vehicle) -> Vehicle:
        model = await self._session.scalar(
            select(VehicleModel).where(
                VehicleModel.id == vehicle.id,
                VehicleModel.shop_id == vehicle.shop_id,
            )
        )
        if model is None:
            raise ValueError("Vehicle not found")
        model.customer_id = vehicle.customer_id
        model.vin = vehicle.vin
        model.license_plate = vehicle.license_plate
        model.year = vehicle.year
        model.make = vehicle.make
        model.model = vehicle.model
        model.mileage = vehicle.mileage
        await self._session.flush()
        await self._session.refresh(model)
        return _vehicle(model)

    async def get_by_id(self, shop_id: UUID, vehicle_id: UUID) -> Vehicle | None:
        row = await self._session.scalar(
            select(VehicleModel).where(
                VehicleModel.id == vehicle_id,
                VehicleModel.shop_id == shop_id,
            )
        )
        return _vehicle(row) if row else None

    async def list_by_customer(self, shop_id: UUID, customer_id: UUID) -> list[Vehicle]:
        rows = await self._session.scalars(
            select(VehicleModel)
            .where(
                VehicleModel.shop_id == shop_id,
                VehicleModel.customer_id == customer_id,
            )
            .order_by(VehicleModel.created_at.desc())
        )
        return [_vehicle(r) for r in rows]

    async def get_by_vin(self, shop_id: UUID, vin: str) -> Vehicle | None:
        row = await self._session.scalar(
            select(VehicleModel).where(
                VehicleModel.shop_id == shop_id,
                VehicleModel.vin == vin.upper(),
            )
        )
        return _vehicle(row) if row else None

    async def get_by_license_plate(self, shop_id: UUID, plate: str) -> Vehicle | None:
        normalized = "".join(ch for ch in plate.strip().upper() if ch.isalnum())
        if not normalized:
            return None
        rows = await self._session.scalars(
            select(VehicleModel)
            .where(
                VehicleModel.shop_id == shop_id,
                VehicleModel.license_plate.is_not(None),
            )
            .order_by(VehicleModel.created_at.desc())
        )
        for row in rows:
            stored = "".join(
                ch for ch in (row.license_plate or "").strip().upper() if ch.isalnum()
            )
            if stored == normalized:
                return _vehicle(row)
        return None

    async def find_by_year_make_model(
        self, shop_id: UUID, year: int, make: str, model: str
    ) -> list[Vehicle]:
        rows = await self._session.scalars(
            select(VehicleModel)
            .where(
                VehicleModel.shop_id == shop_id,
                VehicleModel.year == year,
                VehicleModel.make.ilike(make.strip()),
                VehicleModel.model.ilike(model.strip()),
            )
            .order_by(VehicleModel.created_at.desc())
            .limit(20)
        )
        return [_vehicle(r) for r in rows]


class SqlAlchemyRepairHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: RepairHistory) -> RepairHistory:
        kwargs: dict = {
            "id": entry.id,
            "shop_id": entry.shop_id,
            "customer_id": entry.customer_id,
            "vehicle_id": entry.vehicle_id,
            "service_type": entry.service_type,
            "description": entry.description,
            "cost": entry.cost,
            "recommendation": entry.recommendation,
        }
        # Only set when provided so server_default=now() still applies for new entries.
        if entry.created_at is not None:
            kwargs["created_at"] = entry.created_at
        model = RepairHistoryModel(**kwargs)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _repair(model)

    async def list_by_vehicle(self, shop_id: UUID, vehicle_id: UUID) -> list[RepairHistory]:
        rows = await self._session.scalars(
            select(RepairHistoryModel)
            .where(
                RepairHistoryModel.shop_id == shop_id,
                RepairHistoryModel.vehicle_id == vehicle_id,
            )
            .order_by(RepairHistoryModel.created_at.desc())
        )
        return [_repair(r) for r in rows]


class SqlAlchemyCommunicationHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: CommunicationHistory) -> CommunicationHistory:
        kwargs: dict = {
            "id": entry.id,
            "shop_id": entry.shop_id,
            "customer_id": entry.customer_id,
            "channel": entry.channel.value,
            "message": entry.message,
            "direction": entry.direction.value,
        }
        if entry.created_at is not None:
            kwargs["created_at"] = entry.created_at
        model = CommunicationHistoryModel(**kwargs)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _communication(model)

    async def list_by_customer(
        self, shop_id: UUID, customer_id: UUID
    ) -> list[CommunicationHistory]:
        rows = await self._session.scalars(
            select(CommunicationHistoryModel)
            .where(
                CommunicationHistoryModel.shop_id == shop_id,
                CommunicationHistoryModel.customer_id == customer_id,
            )
            .order_by(CommunicationHistoryModel.created_at.desc())
        )
        return [_communication(r) for r in rows]


class SqlAlchemyWalkInVisitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, visit: WalkInVisit) -> WalkInVisit:
        model = WalkInVisitModel(
            id=visit.id,
            shop_id=visit.shop_id,
            vehicle_id=visit.vehicle_id,
            customer_id=visit.customer_id,
            complaint=visit.complaint,
            status=visit.status.value,
            arrived_at=visit.arrived_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _walk_in(model)

    async def update(self, visit: WalkInVisit) -> WalkInVisit:
        model = await self._session.scalar(
            select(WalkInVisitModel).where(
                WalkInVisitModel.id == visit.id,
                WalkInVisitModel.shop_id == visit.shop_id,
            )
        )
        if model is None:
            raise ValueError("Walk-in visit not found")
        model.vehicle_id = visit.vehicle_id
        model.customer_id = visit.customer_id
        model.complaint = visit.complaint
        model.status = visit.status.value
        model.arrived_at = visit.arrived_at or model.arrived_at
        await self._session.flush()
        await self._session.refresh(model)
        return _walk_in(model)

    async def get_by_id(self, shop_id: UUID, visit_id: UUID) -> WalkInVisit | None:
        row = await self._session.scalar(
            select(WalkInVisitModel).where(
                WalkInVisitModel.id == visit_id,
                WalkInVisitModel.shop_id == shop_id,
            )
        )
        return _walk_in(row) if row else None

    async def list_by_shop(self, shop_id: UUID, status: str | None = None) -> list[WalkInVisit]:
        stmt = select(WalkInVisitModel).where(WalkInVisitModel.shop_id == shop_id)
        if status:
            stmt = stmt.where(WalkInVisitModel.status == status)
        stmt = stmt.order_by(WalkInVisitModel.arrived_at.desc())
        rows = await self._session.scalars(stmt)
        return [_walk_in(r) for r in rows]


class SqlAlchemyVoiceNoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, note: VoiceNote) -> VoiceNote:
        model = VoiceNoteModel(
            id=note.id,
            shop_id=note.shop_id,
            employee_id=note.employee_id,
            audio_url=note.audio_url,
            transcript=note.transcript,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _voice_note(model)

    async def update(self, note: VoiceNote) -> VoiceNote:
        model = await self._session.scalar(
            select(VoiceNoteModel).where(
                VoiceNoteModel.id == note.id,
                VoiceNoteModel.shop_id == note.shop_id,
            )
        )
        if model is None:
            raise ValueError("Voice note not found")
        model.audio_url = note.audio_url
        model.transcript = note.transcript
        await self._session.flush()
        await self._session.refresh(model)
        return _voice_note(model)

    async def get_by_id(self, shop_id: UUID, note_id: UUID) -> VoiceNote | None:
        row = await self._session.scalar(
            select(VoiceNoteModel).where(
                VoiceNoteModel.id == note_id,
                VoiceNoteModel.shop_id == shop_id,
            )
        )
        return _voice_note(row) if row else None

    async def list_by_shop(self, shop_id: UUID) -> list[VoiceNote]:
        rows = await self._session.scalars(
            select(VoiceNoteModel)
            .where(VoiceNoteModel.shop_id == shop_id)
            .order_by(VoiceNoteModel.created_at.desc())
        )
        return [_voice_note(r) for r in rows]
