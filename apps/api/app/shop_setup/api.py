"""Shop Setup Wizard + Service Catalog HTTP API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, require_owner
from app.domain.exceptions import NotFoundError, ValidationError
from app.infrastructure.database import get_session
from app.shop_setup.schemas import (
    CompleteSetupRequest,
    PhoneSchedulingCatalogOut,
    ServiceIn,
    ServiceOut,
    ServiceUpdate,
    SetupStateOut,
    SetupStatusOut,
    UpdateShopSettingsRequest,
)
from app.shop_setup.service import ShopSetupService

router = APIRouter(prefix="/v1/shop", tags=["shop-setup"])


async def _bind_shop(session: AsyncSession, shop_id: UUID) -> ShopSetupService:
    await session.execute(
        text("SELECT set_config('app.shop_id', :sid, true)"),
        {"sid": str(shop_id)},
    )
    return ShopSetupService(session)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


@router.get("/setup", response_model=SetupStateOut)
async def get_setup_state(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SetupStateOut:
    """Full wizard state: profile, hours, services, completion status."""
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.get_state(current.shop_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/setup/status", response_model=SetupStatusOut)
async def get_setup_status(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusOut:
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.get_status(current.shop_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/setup/complete", response_model=SetupStateOut)
async def complete_setup(
    body: CompleteSetupRequest,
    current: CurrentUser = Depends(require_owner()),
    session: AsyncSession = Depends(get_session),
) -> SetupStateOut:
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.complete_setup(current.shop_id, body)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.patch("/settings", response_model=SetupStateOut)
async def update_shop_settings(
    body: UpdateShopSettingsRequest,
    current: CurrentUser = Depends(require_owner()),
    session: AsyncSession = Depends(get_session),
) -> SetupStateOut:
    """Editable shop settings (info + business hours)."""
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.update_settings(current.shop_id, body)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    active_only: bool = Query(default=False),
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ServiceOut]:
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.list_services(current.shop_id, active_only=active_only)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceIn,
    current: CurrentUser = Depends(require_owner()),
    session: AsyncSession = Depends(get_session),
) -> ServiceOut:
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.create_service(current.shop_id, body)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: UUID,
    body: ServiceUpdate,
    current: CurrentUser = Depends(require_owner()),
    session: AsyncSession = Depends(get_session),
) -> ServiceOut:
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.update_service(current.shop_id, service_id, body)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    current: CurrentUser = Depends(require_owner()),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        svc = await _bind_shop(session, current.shop_id)
        await svc.delete_service(current.shop_id, service_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc


@router.get("/phone-catalog", response_model=PhoneSchedulingCatalogOut)
async def phone_scheduling_catalog(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PhoneSchedulingCatalogOut:
    """AI phone scheduling payload: active services + hours + shop contact."""
    try:
        svc = await _bind_shop(session, current.shop_id)
        return await svc.phone_scheduling_catalog(current.shop_id)
    except Exception as exc:  # noqa: BLE001
        raise _http(exc) from exc
