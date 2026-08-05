from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.auth.otp import normalize_email, normalize_phone
from app.core.permissions.permission_service import get_permission_service
from app.core.permissions.user_capabilities import default_capabilities_for_role
from app.domain.entities import RefreshToken, Shop, ShopMembership, User
from app.domain.enums import AccountType, UserRole, normalize_user_role
from app.domain.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.domain.repositories import UnitOfWork
from app.infrastructure.config import settings
from app.infrastructure.security import (
    create_access_token,
    create_mfa_pending_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_expiry,
    verify_password,
)

logger = logging.getLogger("asa.auth")

PLATFORM_ADMIN_ROLE = AccountType.PLATFORM_ADMIN.value


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: UUID
    shop_id: UUID | None
    role: str
    primary_auth_method: str
    username: str | None
    phone: str | None
    email: str | None
    full_name: str
    shop_name: str
    shop_slug: str
    capabilities: list[str]
    account_type: str = AccountType.SHOP.value
    mfa_required: bool = False
    mfa_token: str | None = None


@dataclass(slots=True)
class MeResult:
    user_id: UUID
    primary_auth_method: str
    username: str | None
    phone: str | None
    email: str | None
    full_name: str
    shop_id: UUID
    shop_name: str
    shop_slug: str
    role: UserRole
    capabilities: list[str]
    phone_verified: bool
    email_verified: bool
    mfa_enabled: bool = False


class AuthService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def register_shop(
        self,
        *,
        shop_name: str,
        shop_slug: str,
        owner_full_name: str,
        password: str,
        auth_method: str = "phone",
        owner_phone: str | None = None,
        owner_email: str | None = None,
        timezone: str = "America/Los_Angeles",
    ) -> AuthTokens:
        method = (auth_method or "phone").lower().strip()
        if method not in {"phone", "email"}:
            raise ValidationError("auth_method must be phone or email")

        phone: str | None = None
        email: str | None = None
        phone_verified = False
        email_verified = False

        if method == "phone":
            phone = normalize_phone(owner_phone or "")
            phone_verified = True
            if owner_email:
                email = normalize_email(str(owner_email))
                email_verified = True
        else:
            email = normalize_email(str(owner_email or ""))
            email_verified = True
            if owner_phone:
                phone = normalize_phone(owner_phone)
                phone_verified = True

        if await self._uow.shops.get_by_slug(shop_slug):
            raise ConflictError("Shop slug already taken")
        if phone and await self._uow.users.get_by_phone(phone):
            raise ConflictError("Phone already registered")
        if email and await self._uow.users.get_by_email(email):
            raise ConflictError("Email already registered")

        shop = Shop(id=uuid4(), name=shop_name, slug=shop_slug, timezone=timezone)
        user = User(
            id=uuid4(),
            phone=phone,
            email=email,
            full_name=owner_full_name,
            password_hash=hash_password(password),
            phone_verified=phone_verified,
            email_verified=email_verified,
            primary_auth_method=method,
            account_type=AccountType.SHOP.value,
        )
        await self._uow.shops.add(shop)
        await self._uow.users.add(user)
        await self._uow.memberships.add(
            ShopMembership(
                id=uuid4(),
                shop_id=shop.id,
                user_id=user.id,
                role=UserRole.OWNER,
                capabilities=default_capabilities_for_role(UserRole.OWNER),
            )
        )
        # Seed shop contact from owner so Settings/Setup do not require re-entry.
        try:
            from app.shop_setup.models import ShopSetupProfileModel

            now = datetime.now(timezone.utc)
            self._uow._session.add(
                ShopSetupProfileModel(
                    shop_id=shop.id,
                    phone=phone,
                    email=email,
                    country="US",
                    created_at=now,
                    updated_at=now,
                )
            )
        except Exception:
            pass
        tokens = await self._issue_tokens(
            user=user,
            shop=shop,
            role=UserRole.OWNER,
            capabilities=default_capabilities_for_role(UserRole.OWNER),
        )
        await self._uow.commit()
        try:
            from app.saas.billing import BillingService

            await BillingService().ensure_subscription(shop.id, plan_id="free")
        except Exception:
            pass
        signup_payload = {
            "shop_slug": shop.slug,
            "shop_name": shop.name,
            "owner_email": user.email,
            "owner_phone": user.phone,
            "owner_full_name": user.full_name,
            "joined_by": user.full_name,
            "user_id": str(user.id),
            "role": UserRole.OWNER.value,
            "plan_id": "free",
        }
        contact = user.email or user.phone or ""
        signup_message = (
            f"shop={shop.slug} joined_by={user.full_name} role=owner contact={contact}"
        ).strip()
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=shop.id,
                event_type=DomainEventType.SAAS_SIGNUP,
                payload=signup_payload,
                source="auth",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("saas.signup.emit_failed shop=%s err=%s", shop.slug, exc)
        # Ensure Admin Notification Center always gets the signup even if the
        # workflow observer path fails. Same dedupe_key as the event bridge.
        try:
            from app.admin.notifications import AdminNotificationService
            from app.workflows.enums import DomainEventType

            await AdminNotificationService().create(
                event_type=DomainEventType.SAAS_SIGNUP.value,
                title="New signup",
                message=signup_message,
                severity="info",
                source="auth",
                shop_id=shop.id,
                payload={**signup_payload, "kind": "new_signup", "domain_event_type": "saas.signup"},
                dedupe_key=f"saas.signup:{shop.id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("saas.signup.notify_failed shop=%s err=%s", shop.slug, exc)
        return tokens

    async def login(
        self,
        *,
        password: str,
        shop_slug: str,
        phone: str | None = None,
        email: str | None = None,
    ) -> AuthTokens:
        user: User | None = None
        if phone:
            user = await self._uow.users.get_by_phone(normalize_phone(phone))
        elif email:
            user = await self._uow.users.get_by_email(normalize_email(email))
        else:
            raise ValidationError("phone or email is required")

        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")
        if (user.account_type or AccountType.SHOP.value) == AccountType.PLATFORM_ADMIN.value:
            raise AuthenticationError("Use admin sign-in for platform admin accounts")

        # Password already proved identity. Heal stale verified flags so contacts
        # added/changed in Settings (which previously left verified=false) can log in.
        if phone and not user.phone_verified:
            await self._uow.users.set_phone_verified(user.id, True)
            user.phone_verified = True
        if email and not user.email_verified:
            await self._uow.users.set_email_verified(user.id, True)
            user.email_verified = True

        shop = await self._uow.shops.get_by_slug(shop_slug)
        if shop is None:
            raise NotFoundError("Shop not found")

        membership = await self._uow.memberships.get(shop.id, user.id)
        if membership is None:
            raise AuthenticationError("Not a member of this shop")

        # Enterprise SSO enforcement: password login blocked when org requires SSO.
        try:
            from app.enterprise.factory import get_enterprise_runtime

            rt = get_enterprise_runtime()
            loc = rt.store.find_location_by_shop_id(shop.id)
            if loc is not None:
                sso = rt.store.get_sso(loc.organization_id)
                if sso and sso.enabled and sso.require_sso:
                    raise AuthenticationError(
                        "This shop requires SSO. Sign in with your organization identity provider."
                    )
        except AuthenticationError:
            raise
        except Exception:
            pass

        role = normalize_user_role(membership.role)
        caps = get_permission_service().resolve_capabilities(
            role=role,
            stored_capabilities=membership.capabilities,
        )
        is_first_login = not await self._uow.refresh_tokens.exists_for_user_shop(
            user.id, shop.id
        )
        if user.mfa_enabled and user.mfa_secret:
            pending = create_mfa_pending_token(user_id=user.id, shop_id=shop.id)
            return AuthTokens(
                access_token="",
                refresh_token="",
                token_type="bearer",
                expires_in=0,
                user_id=user.id,
                shop_id=shop.id,
                role=role.value,
                primary_auth_method=user.primary_auth_method or "phone",
                username=user.username,
                phone=user.phone,
                email=user.email,
                full_name=user.full_name,
                shop_name=shop.name,
                shop_slug=shop.slug,
                capabilities=caps,
                account_type=AccountType.SHOP.value,
                mfa_required=True,
                mfa_token=pending,
            )
        tokens = await self._issue_tokens(user=user, shop=shop, role=role, capabilities=caps)
        await self._uow.commit()
        if is_first_login:
            try:
                from app.admin.saas_notify import notify_member_joined

                await notify_member_joined(
                    shop_id=shop.id,
                    shop_slug=shop.slug,
                    shop_name=shop.name,
                    user_id=user.id,
                    full_name=user.full_name,
                    role=role.value,
                    phone=user.phone,
                    email=user.email,
                    joined_via="login",
                    source="auth",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "saas.member_joined.login_notify_failed shop=%s user=%s err=%s",
                    shop.slug,
                    user.id,
                    exc,
                )
        return tokens

    async def login_platform_admin(
        self,
        *,
        username: str,
        password: str,
    ) -> AuthTokens:
        normalized = (username or "").strip().lower()
        if not normalized:
            raise ValidationError("username is required")
        if not password:
            raise ValidationError("password is required")

        allowlist = settings.platform_admin_username_set
        if settings.environment.lower() in {"production", "prod"} and not allowlist:
            raise AuthenticationError("Platform admin required")
        if normalized not in allowlist:
            raise AuthenticationError("Platform admin required")

        user = await self._uow.users.get_by_username(normalized)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        if (user.account_type or AccountType.SHOP.value) != AccountType.PLATFORM_ADMIN.value:
            updated = await self._uow.users.update_account_type(
                user.id, account_type=AccountType.PLATFORM_ADMIN.value
            )
            if updated is None:
                raise AuthenticationError("Platform admin required")
            user = updated

        if user.mfa_enabled and user.mfa_secret:
            pending = create_mfa_pending_token(
                user_id=user.id,
                account_type=AccountType.PLATFORM_ADMIN.value,
            )
            return AuthTokens(
                access_token="",
                refresh_token="",
                token_type="bearer",
                expires_in=0,
                user_id=user.id,
                shop_id=None,
                role=PLATFORM_ADMIN_ROLE,
                primary_auth_method=user.primary_auth_method or "username",
                username=user.username,
                phone=user.phone,
                email=user.email,
                full_name=user.full_name,
                shop_name="",
                shop_slug="",
                capabilities=[],
                account_type=AccountType.PLATFORM_ADMIN.value,
                mfa_required=True,
                mfa_token=pending,
            )

        tokens = await self._issue_admin_tokens(user=user)
        await self._uow.commit()
        return tokens

    async def complete_mfa(self, *, mfa_token: str, code: str) -> AuthTokens:
        from app.saas.mfa import consume_backup_code, verify_totp

        try:
            payload = decode_token(mfa_token)
            if payload.get("type") != "mfa_pending":
                raise ValueError("bad type")
            user_id = UUID(payload["sub"])
            account_type = str(payload.get("account_type") or AccountType.SHOP.value).strip().lower()
            raw_shop = payload.get("shop_id")
            shop_id = UUID(raw_shop) if raw_shop else None
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthenticationError("Invalid MFA token") from exc

        user = await self._uow.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid MFA token")
        if not user.mfa_enabled or not user.mfa_secret:
            raise AuthenticationError("Invalid MFA code")

        ok = verify_totp(user.mfa_secret, code)
        if not ok:
            used, updated = consume_backup_code(user.mfa_backup_codes_json, code)
            if not used:
                raise AuthenticationError("Invalid MFA code")
            await self._uow.users.set_mfa_backup_codes(user.id, updated)

        if account_type == AccountType.PLATFORM_ADMIN.value or (
            user.account_type or ""
        ) == AccountType.PLATFORM_ADMIN.value:
            if (user.username or "").strip().lower() not in settings.platform_admin_username_set:
                raise AuthenticationError("Platform admin required")
            tokens = await self._issue_admin_tokens(user=user)
            await self._uow.commit()
            return tokens

        if shop_id is None:
            raise AuthenticationError("Invalid MFA token")
        shop = await self._uow.shops.get_by_id(shop_id)
        if shop is None:
            raise AuthenticationError("Invalid MFA token")

        membership = await self._uow.memberships.get(shop.id, user.id)
        if membership is None:
            raise AuthenticationError("Not a member of this shop")
        role = normalize_user_role(membership.role)
        caps = get_permission_service().resolve_capabilities(
            role=role,
            stored_capabilities=membership.capabilities,
        )
        is_first_login = not await self._uow.refresh_tokens.exists_for_user_shop(
            user.id, shop.id
        )
        tokens = await self._issue_tokens(user=user, shop=shop, role=role, capabilities=caps)
        await self._uow.commit()
        if is_first_login:
            try:
                from app.admin.saas_notify import notify_member_joined

                await notify_member_joined(
                    shop_id=shop.id,
                    shop_slug=shop.slug,
                    shop_name=shop.name,
                    user_id=user.id,
                    full_name=user.full_name,
                    role=role.value,
                    phone=user.phone,
                    email=user.email,
                    joined_via="login",
                    source="auth",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "saas.member_joined.mfa_notify_failed shop=%s user=%s err=%s",
                    shop.slug,
                    user.id,
                    exc,
                )
        return tokens

    async def begin_mfa_setup(self, *, user_id: UUID) -> dict:
        from app.saas.mfa import generate_mfa_secret, provisioning_uri

        user = await self._uow.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        secret = generate_mfa_secret()
        await self._uow.users.set_mfa(user_id, secret=secret, enabled=False, backup_codes_json=None)
        await self._uow.commit()
        account = user.username or user.email or user.phone or str(user.id)
        return {
            "secret": secret,
            "otpauth_url": provisioning_uri(secret=secret, account_name=account),
            "mfa_enabled": False,
        }

    async def confirm_mfa_setup(self, *, user_id: UUID, code: str) -> dict:
        from app.saas.mfa import generate_backup_codes, verify_totp

        user = await self._uow.users.get_by_id(user_id)
        if user is None or not user.mfa_secret:
            raise ValidationError("Start MFA setup first")
        if not verify_totp(user.mfa_secret, code):
            raise AuthenticationError("Invalid MFA code")
        plain, hashed_json = generate_backup_codes()
        await self._uow.users.set_mfa(
            user_id,
            secret=user.mfa_secret,
            enabled=True,
            backup_codes_json=hashed_json,
        )
        await self._uow.commit()
        return {"mfa_enabled": True, "backup_codes": plain}

    async def regenerate_mfa_backup_codes(self, *, user_id: UUID, code: str) -> dict:
        from app.saas.mfa import generate_backup_codes, verify_totp

        user = await self._uow.users.get_by_id(user_id)
        if user is None or not user.mfa_enabled or not user.mfa_secret:
            raise ValidationError("MFA is not enabled")
        if not verify_totp(user.mfa_secret, code):
            raise AuthenticationError("Invalid MFA code")
        plain, hashed_json = generate_backup_codes()
        await self._uow.users.set_mfa_backup_codes(user_id, hashed_json)
        await self._uow.commit()
        return {"backup_codes": plain}

    async def disable_mfa(self, *, user_id: UUID, code: str) -> dict:
        from app.saas.mfa import consume_backup_code, verify_totp

        user = await self._uow.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if user.mfa_enabled and user.mfa_secret:
            ok = verify_totp(user.mfa_secret, code)
            if not ok:
                used, _ = consume_backup_code(user.mfa_backup_codes_json, code)
                if not used:
                    raise AuthenticationError("Invalid MFA code")
        await self._uow.users.set_mfa(user_id, secret=None, enabled=False, backup_codes_json=None)
        await self._uow.commit()
        return {"mfa_enabled": False}

    async def refresh(self, *, raw_refresh_token: str) -> AuthTokens:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._uow.refresh_tokens.get_by_hash(token_hash)
        now = datetime.now(timezone.utc)
        if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
            raise AuthenticationError("Invalid refresh token")

        user = await self._uow.users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid refresh token")

        # Atomic revoke: if logout already cleared this token, do not mint a new session.
        if not await self._uow.refresh_tokens.revoke(stored.id, now):
            raise AuthenticationError("Invalid refresh token")

        if (user.account_type or AccountType.SHOP.value) == AccountType.PLATFORM_ADMIN.value:
            if (user.username or "").strip().lower() not in settings.platform_admin_username_set:
                raise AuthenticationError("Invalid refresh token")
            tokens = await self._issue_admin_tokens(user=user)
            await self._uow.commit()
            return tokens

        if stored.shop_id is None:
            raise AuthenticationError("Invalid refresh token")
        shop = await self._uow.shops.get_by_id(stored.shop_id)
        if shop is None:
            raise AuthenticationError("Invalid refresh token")

        membership = await self._uow.memberships.get(shop.id, user.id)
        if membership is None:
            raise AuthenticationError("Invalid refresh token")

        role = normalize_user_role(membership.role)
        caps = get_permission_service().resolve_capabilities(
            role=role,
            stored_capabilities=membership.capabilities,
        )
        tokens = await self._issue_tokens(user=user, shop=shop, role=role, capabilities=caps)
        await self._uow.commit()
        return tokens

    async def logout(self, *, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._uow.refresh_tokens.get_by_hash(token_hash)
        if stored is None:
            return
        # Revoke every live session for this user so admin presence clears immediately
        # even if another tab rotated tokens during logout.
        await self._uow.refresh_tokens.revoke_all_for_user(
            stored.user_id, datetime.now(timezone.utc)
        )
        await self._uow.commit()

    async def me(
        self,
        *,
        user_id: UUID,
        shop_id: UUID,
        role: UserRole,
        capabilities: list[str] | None = None,
    ) -> MeResult:
        user = await self._uow.users.get_by_id(user_id)
        if user is not None and (user.account_type or "") == AccountType.PLATFORM_ADMIN.value:
            raise AuthenticationError("Shop profile unavailable for platform admin")
        shop = await self._uow.shops.get_by_id(shop_id)
        if user is None or shop is None:
            raise NotFoundError("User or shop not found")
        caps = capabilities
        if caps is None:
            membership = await self._uow.memberships.get(shop_id, user_id)
            caps = get_permission_service().resolve_capabilities(
                role=role,
                stored_capabilities=membership.capabilities if membership else None,
            )
        return MeResult(
            user_id=user.id,
            primary_auth_method=user.primary_auth_method or "phone",
            username=user.username,
            phone=user.phone,
            email=user.email,
            full_name=user.full_name,
            shop_id=shop.id,
            shop_name=shop.name,
            shop_slug=shop.slug,
            role=normalize_user_role(role),
            capabilities=list(caps or []),
            phone_verified=bool(user.phone_verified),
            email_verified=bool(user.email_verified),
            mfa_enabled=bool(user.mfa_enabled),
        )

    async def _issue_tokens(
        self,
        *,
        user: User,
        shop: Shop,
        role: UserRole,
        capabilities: list[str] | None = None,
    ) -> AuthTokens:
        role = normalize_user_role(role)
        caps = capabilities or default_capabilities_for_role(role)
        method = user.primary_auth_method or ("phone" if user.phone else "email")
        access = create_access_token(
            subject=str(user.id),
            shop_id=shop.id,
            role=role.value,
            account_type=AccountType.SHOP.value,
            username=user.username,
            email=user.email,
            phone=user.phone,
            capabilities=caps,
        )
        raw_refresh = generate_refresh_token()
        await self._uow.refresh_tokens.add(
            RefreshToken(
                id=uuid4(),
                user_id=user.id,
                shop_id=shop.id,
                token_hash=hash_refresh_token(raw_refresh),
                expires_at=refresh_expiry(),
            )
        )
        return AuthTokens(
            access_token=access,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user_id=user.id,
            shop_id=shop.id,
            role=role.value,
            primary_auth_method=method,
            username=user.username,
            phone=user.phone,
            email=user.email,
            full_name=user.full_name,
            shop_name=shop.name,
            shop_slug=shop.slug,
            capabilities=list(caps),
            account_type=AccountType.SHOP.value,
        )

    async def _issue_admin_tokens(self, *, user: User) -> AuthTokens:
        method = user.primary_auth_method or "username"
        access = create_access_token(
            subject=str(user.id),
            shop_id=None,
            role=PLATFORM_ADMIN_ROLE,
            account_type=AccountType.PLATFORM_ADMIN.value,
            username=user.username,
            email=user.email,
            phone=user.phone,
            capabilities=[],
        )
        raw_refresh = generate_refresh_token()
        await self._uow.refresh_tokens.add(
            RefreshToken(
                id=uuid4(),
                user_id=user.id,
                shop_id=None,
                token_hash=hash_refresh_token(raw_refresh),
                expires_at=refresh_expiry(),
            )
        )
        return AuthTokens(
            access_token=access,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user_id=user.id,
            shop_id=None,
            role=PLATFORM_ADMIN_ROLE,
            primary_auth_method=method,
            username=user.username,
            phone=user.phone,
            email=user.email,
            full_name=user.full_name,
            shop_name="",
            shop_slug="",
            capabilities=[],
            account_type=AccountType.PLATFORM_ADMIN.value,
        )
