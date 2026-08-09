"""Admin console HTTP API — /v1/admin/* (platform allowlist auth)."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.admin.deps import require_platform_admin
from app.admin.service import AdminConsoleService
from app.admin.settings import EditableSettingsPatch, PlatformSettingsService
from app.api.deps import CurrentUser, get_current_user, get_uow
from app.domain.exceptions import ConflictError, NotFoundError, ValidationError
from app.infrastructure.security import hash_password, verify_password
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

router = APIRouter(prefix="/v1/admin", tags=["admin"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _svc() -> AdminConsoleService:
    return AdminConsoleService()


class AdminProfileOut(BaseModel):
    user_id: UUID
    username: str
    full_name: str


class UpdateAdminProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class ChangeAdminPasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class InitializeMemberPasswordRequest(BaseModel):
    """Optional custom password; omit to auto-generate a temporary password."""

    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class DeleteAdminNotificationsRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


class ChangeOrganizationPlanRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)


class AssignOrganizationTwilioNumberRequest(BaseModel):
    """Omit phone_e164 to auto-provision; set phone_e164 for a manual E.164 assign."""

    phone_e164: str | None = Field(default=None, max_length=32)


async def _fingerprint_sse(
    request: Request,
    *,
    event_name: str,
    fetch,
    fingerprint,
):
    """Yield SSE events when fingerprint changes; otherwise ping.

    Pings/updates are flushed every poll tick so proxies/browsers keep the
    stream live while the admin stays on the page.
    """
    last_fp = ""
    # First payload ASAP so the UI marks Live before the first sleep.
    while True:
        if await request.is_disconnected():
            break
        poll = await PlatformSettingsService().dashboard_poll_seconds()
        try:
            data = await fetch()
        except Exception:
            yield f"event: ping\ndata: {json.dumps({'ok': False})}\n\n"
            await asyncio.sleep(poll)
            continue
        if data is None:
            yield f"event: ping\ndata: {json.dumps({'ok': True})}\n\n"
            await asyncio.sleep(poll)
            continue
        fp = fingerprint(data)
        if fp != last_fp:
            last_fp = fp
            yield f"event: {event_name}\ndata: {json.dumps(data, default=str)}\n\n"
        else:
            yield f"event: ping\ndata: {json.dumps({'ok': True})}\n\n"
        await asyncio.sleep(poll)


@router.get("/dashboard")
async def admin_dashboard(_: str = Depends(require_platform_admin)) -> dict:
    return await _svc().dashboard()


@router.get("/dashboard/stream")
async def admin_dashboard_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when dashboard KPI fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="dashboard",
            fetch=svc.dashboard,
            fingerprint=svc.dashboard_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/organizations")
async def admin_organizations(_: str = Depends(require_platform_admin)) -> dict:
    return await _svc().organizations()


@router.get("/organizations/stream")
async def admin_organizations_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when organization list fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="organizations",
            fetch=svc.organizations,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/organizations/{shop_id}/stream")
async def admin_organization_detail_stream(
    shop_id: str,
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when a single organization detail fingerprint changes."""
    svc = _svc()

    async def fetch():
        return await svc.organization_detail(shop_id)

    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="organization",
            fetch=fetch,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/organizations/{shop_id}")
async def admin_organization_detail(
    shop_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    detail = await _svc().organization_detail(shop_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return detail


@router.get("/organizations/{shop_id}/usage")
async def admin_organization_usage(
    shop_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    detail = await _svc().organization_detail(shop_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return detail["usage"]


@router.post("/organizations/{shop_id}/plan")
async def admin_organization_change_plan(
    shop_id: str,
    body: ChangeOrganizationPlanRequest,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        return await _svc().change_organization_plan(shop_id, body.plan_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/twilio-number")
async def admin_organization_assign_twilio_number(
    shop_id: str,
    body: AssignOrganizationTwilioNumberRequest = Body(
        default_factory=AssignOrganizationTwilioNumberRequest
    ),
    _: str = Depends(require_platform_admin),
) -> dict:
    """Assign a Twilio SMS/Voice number to a shop (manual E.164 or auto-provision)."""
    try:
        return await _svc().assign_organization_twilio_number(
            shop_id, phone_e164=body.phone_e164
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/organizations/{shop_id}/twilio-number")
async def admin_organization_clear_twilio_number(
    shop_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    """Unassign shop↔number in DB only. Never calls Twilio (number stays purchased)."""
    try:
        return await _svc().clear_organization_twilio_number(shop_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/twilio-number/reset")
async def admin_organization_reset_twilio_number(
    shop_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    """Release previous number (best-effort) and assign a newly provisioned one."""
    try:
        return await _svc().reset_organization_twilio_number(shop_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/members/{user_id}/suspend")
async def admin_organization_member_suspend(
    shop_id: str,
    user_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        return await _svc().set_member_active(shop_id, user_id, is_active=False)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/members/{user_id}/activate")
async def admin_organization_member_activate(
    shop_id: str,
    user_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        return await _svc().set_member_active(shop_id, user_id, is_active=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/members/{user_id}/password-reset")
async def admin_organization_member_password_reset(
    shop_id: str,
    user_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        return await _svc().request_member_password_reset(shop_id, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/organizations/{shop_id}/members/{user_id}/password-initialize")
async def admin_organization_member_password_initialize(
    shop_id: str,
    user_id: str,
    body: InitializeMemberPasswordRequest = Body(default_factory=InitializeMemberPasswordRequest),
    _: str = Depends(require_platform_admin),
) -> dict:
    """Set a temporary password for a member. Returns plaintext once for admin to share."""
    try:
        return await _svc().initialize_member_password(
            shop_id,
            user_id,
            new_password=body.new_password,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/billing")
async def admin_billing(_: str = Depends(require_platform_admin)) -> dict:
    return await _svc().billing_monitor()


@router.get("/billing/stream")
async def admin_billing_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when billing monitor fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="billing",
            fetch=svc.billing_monitor,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/usage")
async def admin_usage(_: str = Depends(require_platform_admin)) -> dict:
    """AI token (ai_calls) + SMS usage + voice runtime metrics."""
    return await _svc().token_usage()


@router.get("/usage/stream")
async def admin_usage_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when usage fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="usage",
            fetch=svc.token_usage,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/users")
async def admin_users(_: str = Depends(require_platform_admin)) -> dict:
    return await _svc().users()


@router.get("/users/stream")
async def admin_users_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when membership/online fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="users",
            fetch=svc.users,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/system")
async def admin_system(_: str = Depends(require_platform_admin)) -> dict:
    return await _svc().system_status()


@router.get("/system/stream")
async def admin_system_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when system status fingerprint changes."""
    svc = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="system",
            fetch=svc.system_status,
            fingerprint=svc.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/settings")
async def admin_settings_get(_: str = Depends(require_platform_admin)) -> dict:
    return await PlatformSettingsService().get()


@router.get("/settings/stream")
async def admin_settings_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when platform settings fingerprint changes."""
    settings_svc = PlatformSettingsService()
    console = _svc()
    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="settings",
            fetch=settings_svc.get,
            fingerprint=console.resource_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.patch("/settings")
async def admin_settings_patch(
    body: EditableSettingsPatch,
    username: str = Depends(require_platform_admin),
) -> dict:
    return await PlatformSettingsService().patch(body, updated_by=username)


@router.get("/me", response_model=AdminProfileOut)
async def admin_me_get(
    username: str = Depends(require_platform_admin),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> AdminProfileOut:
    user = await uow.users.get_by_id(current.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminProfileOut(
        user_id=user.id,
        username=username,
        full_name=user.full_name,
    )


@router.patch("/me", response_model=AdminProfileOut)
async def admin_me_patch(
    body: UpdateAdminProfileRequest,
    username: str = Depends(require_platform_admin),
    current: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> AdminProfileOut:
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")

    existing = await uow.users.get_by_id(current.user_id)
    if existing is None or not existing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await uow.users.update_profile(current.user_id, full_name=full_name)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await uow.commit()
    return AdminProfileOut(
        user_id=user.id,
        username=username,
        full_name=user.full_name,
    )


@router.post("/me/password")
async def admin_me_change_password(
    body: ChangeAdminPasswordRequest,
    _: str = Depends(require_platform_admin),
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


@router.get("/notifications")
async def admin_notifications(
    limit: int = Query(default=200, ge=1, le=500),
    event_type: str | None = Query(default=None),
    unread_only: bool = Query(default=False),
    _: str = Depends(require_platform_admin),
) -> dict:
    return await _svc().notification_feed(
        limit=limit,
        event_type=event_type,
        unread_only=unread_only,
    )


@router.post("/notifications/read-all")
async def admin_notifications_mark_all_read(
    _: str = Depends(require_platform_admin),
) -> dict:
    return await _svc().mark_all_notifications_read()


@router.post("/notifications/delete")
async def admin_notifications_bulk_delete(
    body: DeleteAdminNotificationsRequest,
    _: str = Depends(require_platform_admin),
) -> dict:
    return await _svc().delete_notifications(body.ids)


@router.post("/notifications/{notification_id}/read")
async def admin_notification_mark_read(
    notification_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        nid = UUID(notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from exc
    item = await _svc().mark_notification_read(nid)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return item


@router.delete("/notifications/{notification_id}")
async def admin_notification_delete(
    notification_id: str,
    _: str = Depends(require_platform_admin),
) -> dict:
    try:
        nid = UUID(notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id") from exc
    deleted = await _svc().delete_notification(nid)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"deleted": True, "id": notification_id}


@router.get("/notifications/stream")
async def admin_notifications_stream(
    request: Request,
    _: str = Depends(require_platform_admin),
) -> StreamingResponse:
    """SSE feed — pushes when notification store / monitor fingerprint changes."""
    svc = _svc()

    async def fetch():
        return await svc.notification_feed(limit=200)

    return StreamingResponse(
        _fingerprint_sse(
            request,
            event_name="notifications",
            fetch=fetch,
            fingerprint=svc.notification_fingerprint,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
