"""Tenant / shop membership & capability management (Owner-administered)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.admin.saas_notify import notify_contact_changed
from app.api.deps import CurrentUser, get_current_user, get_uow, require_owner
from app.auth.otp import normalize_email, normalize_phone
from app.core.permissions.capabilities import (
    ALL_STAFF_CAPABILITIES,
    CAPABILITY_LABELS,
    StaffCapability,
)
from app.core.permissions.user_capabilities import (
    default_capabilities_for_role,
    parse_capabilities,
)
from app.domain.entities import ShopMembership, User
from app.domain.enums import UserRole, normalize_user_role
from app.domain.exceptions import ValidationError
from app.infrastructure.security import hash_password, verify_password
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.saas.quotas import QuotaService

router = APIRouter(prefix="/v1/tenant", tags=["tenant"])


class CapabilityCatalogItem(BaseModel):
    id: str
    label: str


class MemberOut(BaseModel):
    membership_id: UUID
    user_id: UUID
    phone: str | None = None
    email: str | None = None
    full_name: str
    role: UserRole
    capabilities: list[str]
    phone_verified: bool = False


class InviteStaffRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = None
    capabilities: list[str] | None = None


class UpdateMemberCapabilitiesRequest(BaseModel):
    capabilities: list[str] = Field(min_length=0)


class ShopSettingsOut(BaseModel):
    shop_id: UUID
    name: str
    slug: str
    timezone: str
    sms_phone_e164: str | None = None
    voice_phone_e164: str | None = None
    ai_paused: bool = False
    # True when monthly AI call quota still has remaining capacity.
    ai_usage_available: bool = True


class UpdateShopSettingsRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class SetShopAiPausedRequest(BaseModel):
    ai_paused: bool


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class NotificationPrefsOut(BaseModel):
    email_appointments: bool = True
    email_alerts: bool = True
    sms_alerts: bool = True
    in_app: bool = True


class UpdateNotificationPrefsRequest(BaseModel):
    email_appointments: bool | None = None
    email_alerts: bool | None = None
    sms_alerts: bool | None = None
    in_app: bool | None = None


class ProfileOut(BaseModel):
    user_id: UUID
    full_name: str
    phone: str | None = None
    email: str | None = None
    role: UserRole
    shop_id: UUID
    shop_name: str
    shop_slug: str


def _notification_prefs_out(raw: dict | None) -> NotificationPrefsOut:
    data = raw or {}
    return NotificationPrefsOut(
        email_appointments=bool(data.get("email_appointments", True)),
        email_alerts=bool(data.get("email_alerts", True)),
        sms_alerts=bool(data.get("sms_alerts", True)),
        in_app=bool(data.get("in_app", True)),
    )


def _member_out(m, user: User) -> MemberOut:
    caps = m.capabilities or default_capabilities_for_role(m.role)
    return MemberOut(
        membership_id=m.id,
        user_id=user.id,
        phone=user.phone,
        email=user.email,
        full_name=user.full_name,
        role=normalize_user_role(m.role),
        capabilities=list(caps),
        phone_verified=bool(user.phone_verified),
    )


@router.get("/capabilities", response_model=list[CapabilityCatalogItem])
async def list_capability_catalog(
    _: CurrentUser = Depends(require_owner()),
) -> list[CapabilityCatalogItem]:
    return [
        CapabilityCatalogItem(id=c.value, label=CAPABILITY_LABELS[c])
        for c in ALL_STAFF_CAPABILITIES
    ]


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> list[MemberOut]:
    """Any shop member can view the roster; invite/edit/remove stay owner-only."""
    memberships = await uow.memberships.list_for_shop(current.shop_id)
    out: list[MemberOut] = []
    for m in memberships:
        user = await uow.users.get_by_id(m.user_id)
        if user is None:
            continue
        out.append(_member_out(m, user))
    return out


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def invite_staff(
    body: InviteStaffRequest,
    current: CurrentUser = Depends(require_owner()),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> MemberOut:
    try:
        phone = normalize_phone(body.phone)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    email = str(body.email).lower() if body.email else None
    existing = await uow.users.get_by_phone(phone)
    if existing is not None:
        membership = await uow.memberships.get(current.shop_id, existing.id)
        if membership is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")

    if existing is None and email and await uow.users.get_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Enforce plan seat limit before creating user/membership rows.
    try:
        from app.saas.quotas import QuotaService

        await QuotaService().ensure_seat_available(current.shop_id)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if existing is not None:
        user = existing
    else:
        user = User(
            id=uuid4(),
            phone=phone,
            email=email,
            full_name=body.full_name,
            password_hash=hash_password(body.password),
            # Owner-provisioned invite: phone is the login identity + temp password.
            phone_verified=True,
            email_verified=False,
            primary_auth_method="phone",
        )
        await uow.users.add(user)

    caps = parse_capabilities(body.capabilities) or default_capabilities_for_role(UserRole.STAFF)
    membership = await uow.memberships.add(
        ShopMembership(
            id=uuid4(),
            shop_id=current.shop_id,
            user_id=user.id,
            role=UserRole.STAFF,
            capabilities=caps,
        )
    )
    shop = await uow.shops.get_by_id(current.shop_id)
    await uow.commit()
    if shop is not None:
        try:
            from app.admin.saas_notify import notify_member_joined

            await notify_member_joined(
                shop_id=shop.id,
                shop_slug=shop.slug,
                shop_name=shop.name,
                user_id=user.id,
                full_name=user.full_name,
                role=UserRole.STAFF.value,
                phone=user.phone,
                email=user.email,
                joined_via="invite",
                source="tenant",
            )
        except Exception:  # noqa: BLE001
            pass
    return _member_out(membership, user)


@router.patch("/members/{membership_id}/capabilities", response_model=MemberOut)
async def update_member_capabilities(
    membership_id: UUID,
    body: UpdateMemberCapabilitiesRequest,
    current: CurrentUser = Depends(require_owner()),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> MemberOut:
    memberships = await uow.memberships.list_for_shop(current.shop_id)
    membership = next((m for m in memberships if m.id == membership_id), None)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if normalize_user_role(membership.role) == UserRole.OWNER:
        caps = default_capabilities_for_role(UserRole.OWNER)
    else:
        caps = parse_capabilities(body.capabilities)
        membership.role = UserRole.STAFF
    membership.capabilities = caps
    updated = await uow.memberships.update(membership)
    await uow.commit()
    user = await uow.users.get_by_id(updated.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _member_out(updated, user)


@router.delete("/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: UUID,
    current: CurrentUser = Depends(require_owner()),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> None:
    memberships = await uow.memberships.list_for_shop(current.shop_id)
    membership = next((m for m in memberships if m.id == membership_id), None)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if normalize_user_role(membership.role) == UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the shop owner",
        )
    deleted = await uow.memberships.delete(membership.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await uow.refresh_tokens.revoke_all_for_user(
        membership.user_id, datetime.now(timezone.utc)
    )
    await uow.commit()


@router.get("/me/permissions")
async def my_permissions(current: CurrentUser = Depends(get_current_user)) -> dict:
    return {
        "role": current.role.value,
        "capabilities": list(current.capabilities),
        "phone": current.phone,
        "labels": {
            c.value: CAPABILITY_LABELS[c]
            for c in StaffCapability
            if c.value in current.capabilities or current.role == UserRole.OWNER
        },
        "is_owner": current.role == UserRole.OWNER,
    }


async def _shop_settings_out(uow: SqlAlchemyUnitOfWork, shop) -> ShopSettingsOut:
    sms_phone, voice_phone = await uow.shops.get_channel_phones(shop.id)
    try:
        ai_ok = await QuotaService().ai_usage_available(shop.id)
    except Exception:
        # Fail open for settings reads so quota outages don't break the dashboard.
        ai_ok = True
    return ShopSettingsOut(
        shop_id=shop.id,
        name=shop.name,
        slug=shop.slug,
        timezone=shop.timezone,
        sms_phone_e164=sms_phone,
        voice_phone_e164=voice_phone,
        ai_paused=bool(shop.ai_paused),
        ai_usage_available=bool(ai_ok),
    )


@router.get("/shop", response_model=ShopSettingsOut)
async def get_shop_settings(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> ShopSettingsOut:
    shop = await uow.shops.get_by_id(current.shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return await _shop_settings_out(uow, shop)


@router.patch("/shop", response_model=ShopSettingsOut)
async def update_shop_settings(
    body: UpdateShopSettingsRequest,
    current: CurrentUser = Depends(require_owner()),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> ShopSettingsOut:
    shop = await uow.shops.get_by_id(current.shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    if body.name is None and body.timezone is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")
    if body.name is not None:
        shop.name = body.name.strip()
        if len(shop.name) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shop name too short")
        # Keep internal slug in sync with display name (hidden from owners).
        from app.application.services import AuthService

        shop.slug = await AuthService(uow).allocate_shop_slug(
            shop.name, exclude_shop_id=shop.id
        )
    if body.timezone is not None:
        shop.timezone = body.timezone.strip()
        if not shop.timezone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timezone")
    updated = await uow.shops.update(shop)
    await uow.commit()
    return await _shop_settings_out(uow, updated)


@router.patch("/shop/ai-paused", response_model=ShopSettingsOut)
async def set_shop_ai_paused(
    body: SetShopAiPausedRequest,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> ShopSettingsOut:
    """Pause/resume SMS + Voice AI only. Voice Notes and other AI tools stay on."""
    shop = await uow.shops.get_by_id(current.shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    # Resuming AI requires remaining monthly AI call quota.
    if not body.ai_paused and not await QuotaService().ai_usage_available(shop.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI monthly quota exceeded. Upgrade your plan to resume AI.",
        )
    shop.ai_paused = bool(body.ai_paused)
    updated = await uow.shops.update(shop)
    await uow.commit()
    return await _shop_settings_out(uow, updated)


@router.patch("/me/profile", response_model=ProfileOut)
async def update_my_profile(
    body: UpdateProfileRequest,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> ProfileOut:
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")

    existing = await uow.users.get_by_id(current.user_id)
    if existing is None or not existing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_phone = existing.phone
    new_email = existing.email
    if body.phone is not None:
        raw_phone = body.phone.strip()
        if raw_phone:
            try:
                new_phone = normalize_phone(raw_phone)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
        else:
            new_phone = None
    if body.email is not None:
        raw_email = body.email.strip()
        if raw_email:
            try:
                new_email = normalize_email(raw_email)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
        else:
            new_email = None

    if not new_phone and not new_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone or email is required",
        )
    primary = (existing.primary_auth_method or "phone").lower()
    if primary == "phone" and not new_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone is required for this account",
        )
    if primary == "email" and not new_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required for this account",
        )

    if new_phone and new_phone != existing.phone:
        other = await uow.users.get_by_phone(new_phone)
        if other is not None and other.id != existing.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already in use",
            )
    if new_email and new_email != (existing.email or None):
        other = await uow.users.get_by_email(new_email)
        if other is not None and other.id != existing.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )

    phone_changed = (new_phone or None) != (existing.phone or None)
    email_changed = (new_email or None) != (existing.email or None)

    user = await uow.users.update_profile(
        current.user_id,
        full_name=full_name,
        phone=new_phone,
        email=new_email,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    shop = await uow.shops.get_by_id(current.shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    await uow.commit()

    if phone_changed or email_changed:
        await notify_contact_changed(
            shop_id=shop.id,
            shop_slug=shop.slug,
            shop_name=shop.name,
            user_id=user.id,
            full_name=user.full_name,
            role=str(normalize_user_role(current.role)),
            old_phone=existing.phone,
            new_phone=user.phone,
            old_email=existing.email,
            new_email=user.email,
            source="tenant",
        )

    return ProfileOut(
        user_id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        email=user.email,
        role=normalize_user_role(current.role),
        shop_id=shop.id,
        shop_name=shop.name,
        shop_slug=shop.slug,
    )


@router.post("/me/password")
async def change_my_password(
    body: ChangePasswordRequest,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> dict:
    user = await uow.users.get_by_id(current.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )
    updated = await uow.users.update_password(
        current.user_id, password_hash=hash_password(body.new_password)
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await uow.commit()
    return {"ok": True}


@router.get("/me/notifications", response_model=NotificationPrefsOut)
async def get_my_notifications(
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> NotificationPrefsOut:
    prefs = await uow.users.get_notification_prefs(current.user_id)
    if prefs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _notification_prefs_out(prefs)


@router.patch("/me/notifications", response_model=NotificationPrefsOut)
async def update_my_notifications(
    body: UpdateNotificationPrefsRequest,
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> NotificationPrefsOut:
    current_prefs = await uow.users.get_notification_prefs(current.user_id)
    if current_prefs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    merged = _notification_prefs_out(current_prefs).model_dump()
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")
    merged.update(patch)
    saved = await uow.users.set_notification_prefs(current.user_id, merged)
    if saved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await uow.commit()
    return _notification_prefs_out(saved)
