from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions.capabilities import StaffCapability
from app.core.permissions.permission_service import PermissionDenied, get_permission_service
from app.domain.enums import AccountType, UserRole, normalize_user_role
from app.infrastructure.database import get_session
from app.infrastructure.security import decode_token
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UUID
    shop_id: UUID | None
    role: UserRole | None
    account_type: str = AccountType.SHOP.value
    username: str | None = None
    email: str | None = None
    phone: str | None = None
    capabilities: tuple[str, ...] = ()


async def get_uow(session: AsyncSession = Depends(get_session)) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id = UUID(payload["sub"])
        raw_role = payload.get("role")
        account_type = str(payload.get("account_type") or AccountType.SHOP.value).strip().lower()
        if account_type == AccountType.PLATFORM_ADMIN.value or str(raw_role) == AccountType.PLATFORM_ADMIN.value:
            raw_username = payload.get("username")
            username = str(raw_username).strip().lower() if raw_username else None
            return CurrentUser(
                user_id=user_id,
                shop_id=None,
                role=None,
                account_type=AccountType.PLATFORM_ADMIN.value,
                username=username or None,
                email=payload.get("email"),
                phone=payload.get("phone"),
                capabilities=(),
            )

        shop_id = UUID(payload["shop_id"])
        role = normalize_user_role(raw_role)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None

    # Membership is the source of truth. JWT capabilities/role can go stale after
    # Settings → Team permission edits until the next token refresh.
    stored_caps: list[str] | None = None
    try:
        membership = await uow.memberships.get(shop_id, user_id)
        if membership is not None:
            role = normalize_user_role(membership.role)
            if membership.capabilities is not None:
                stored_caps = list(membership.capabilities)
    except Exception:  # noqa: BLE001
        pass

    if stored_caps is None:
        caps_claim = payload.get("capabilities")
        if isinstance(caps_claim, list):
            stored_caps = [str(c) for c in caps_claim]

    perms = get_permission_service()
    capabilities = tuple(
        perms.resolve_capabilities(
            role=role,
            stored_capabilities=stored_caps,
            legacy_raw_role=str(raw_role),
        )
    )

    await uow.bind_shop(shop_id)
    raw_username = payload.get("username")
    username = str(raw_username).strip().lower() if raw_username else None
    return CurrentUser(
        user_id=user_id,
        shop_id=shop_id,
        role=role,
        account_type=AccountType.SHOP.value,
        username=username or None,
        email=payload.get("email"),
        phone=payload.get("phone"),
        capabilities=capabilities,
    )


def require_capabilities(
    *required: StaffCapability | str,
    require_all: bool = False,
):
    """FastAPI dependency factory — capability-based authorization."""

    async def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role is None or current.shop_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Shop access required",
            )
        try:
            get_permission_service().require(
                role=current.role,
                capabilities=list(current.capabilities),
                required=required,
                require_all=require_all,
            )
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        return current

    return _dep


def require_owner():
    async def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role is None or not get_permission_service().is_owner(current.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner role required",
            )
        return current

    return _dep


def require_dashboard_access():
    async def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role is None or current.shop_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dashboard access denied",
            )
        if not get_permission_service().can_access_dashboard(
            current.role, list(current.capabilities)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dashboard access denied",
            )
        return current

    return _dep


def require_workflow_access():
    async def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current.role is None or current.shop_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workflow access denied",
            )
        if not get_permission_service().can_use_workflows(
            current.role, list(current.capabilities)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workflow access denied",
            )
        return current

    return _dep
