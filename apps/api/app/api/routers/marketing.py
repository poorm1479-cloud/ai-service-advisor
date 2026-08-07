"""Marketing Automation HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_current_user, get_uow
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.marketing.audience import (
    audience_to_dicts,
    list_suggested_action_counts,
    resolve_audience,
)
from app.marketing.enums import CampaignStatus, CampaignType, Channel
from app.marketing.factory import MarketingRuntime, get_marketing_runtime

router = APIRouter(prefix="/v1/marketing", tags=["marketing"])


def _runtime() -> MarketingRuntime:
    return get_marketing_runtime()


def _require_shop_id(user: CurrentUser) -> UUID:
    if user.shop_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Shop access required",
        )
    return user.shop_id


class AudienceIn(BaseModel):
    customer_id: UUID | None = None
    name: str
    phone: str | None = None
    email: str | None = None
    preferred_channel: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignCreate(BaseModel):
    name: str
    campaign_type: CampaignType
    channels_allowed: list[Channel] = Field(default_factory=lambda: [Channel.SMS, Channel.EMAIL])
    audience: list[AudienceIn] | None = None
    custom_message: str | None = None
    scheduled_start: datetime | None = None
    max_sends_per_customer_days: int = 14
    budget: Decimal | None = None
    expected_revenue: Decimal | None = None
    tags: list[str] = Field(default_factory=list)
    use_demo_audience: bool = False
    auto_schedule: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignUpdate(BaseModel):
    name: str | None = None
    custom_message: str | None = None
    status: CampaignStatus | None = None
    channels_allowed: list[Channel] | None = None
    scheduled_start: datetime | None = None
    tags: list[str] | None = None
    budget: Decimal | None = None
    expected_revenue: Decimal | None = None


class TrackRequest(BaseModel):
    event: str
    appointment_id: UUID | None = None
    revenue: Decimal | None = None


class BulkDeleteMessagesRequest(BaseModel):
    message_ids: list[UUID] = Field(default_factory=list, min_length=1)


class AiPlanOut(BaseModel):
    channel: str
    send_at: datetime
    message: str
    subject: str | None
    frequency_days: int
    confidence: float
    reasons: list[str]


class CampaignOut(BaseModel):
    id: UUID
    shop_id: UUID
    name: str
    campaign_type: str
    status: str
    channels_allowed: list[str]
    audience_count: int
    custom_message: str | None
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    ai_defaults: AiPlanOut | None
    max_sends_per_customer_days: int
    budget: str
    expected_revenue: str
    tags: list[str]
    created_at: datetime | None
    updated_at: datetime | None


class CampaignCreateOut(CampaignOut):
    """Campaign create response includes first-customer AI preview to avoid a second round-trip."""

    ai_preview: dict[str, Any] | None = None


class MetricsOut(BaseModel):
    campaign_id: UUID
    shop_id: UUID
    sent: int
    delivered: int
    opened: int
    clicked: int
    replied: int
    appointments: int
    failed: int
    revenue: str
    cost: str
    open_rate: float
    click_rate: float
    reply_rate: float
    appointment_rate: float
    roi: float


class CalendarEventOut(BaseModel):
    campaign_id: UUID
    name: str
    campaign_type: str
    status: str
    day: date
    channel: str | None
    message_count: int


class MessageOut(BaseModel):
    id: UUID
    campaign_id: UUID
    customer_id: UUID
    customer_name: str | None = None
    channel: str
    status: str
    body: str
    subject: str | None
    scheduled_at: datetime | None
    sent_at: datetime | None
    opened_at: datetime | None
    clicked_at: datetime | None
    replied_at: datetime | None
    revenue: str
    attempt: int
    error: str | None


class SuggestedActionOut(BaseModel):
    id: str
    campaign_type: str
    title: str
    description: str
    count: int
    hint: str
    custom_message: str | None = None


def _ai_out(plan) -> AiPlanOut | None:
    if plan is None:
        return None
    return AiPlanOut(
        channel=plan.channel.value,
        send_at=plan.send_at,
        message=plan.message,
        subject=plan.subject,
        frequency_days=plan.frequency_days,
        confidence=plan.confidence,
        reasons=plan.reasons,
    )


def _audience_name_map(campaign) -> dict[UUID, str]:
    return {
        member.customer_id: member.name
        for member in (campaign.audience or [])
        if member.name
    }


def _message_out(m, *, customer_name: str | None = None) -> MessageOut:
    return MessageOut(
        id=m.id,
        campaign_id=m.campaign_id,
        customer_id=m.customer_id,
        customer_name=customer_name,
        channel=m.channel.value,
        status=m.status.value,
        body=m.body,
        subject=m.subject,
        scheduled_at=m.scheduled_at,
        sent_at=m.sent_at,
        opened_at=m.opened_at,
        clicked_at=m.clicked_at,
        replied_at=m.replied_at,
        revenue=str(m.revenue),
        attempt=m.attempt,
        error=m.error,
    )


def _campaign_out(c) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        shop_id=c.shop_id,
        name=c.name,
        campaign_type=c.campaign_type.value,
        status=c.status.value,
        channels_allowed=[ch.value for ch in c.channels_allowed],
        audience_count=len(c.audience),
        custom_message=c.custom_message,
        scheduled_start=c.scheduled_start,
        scheduled_end=c.scheduled_end,
        ai_defaults=_ai_out(c.ai_defaults),
        max_sends_per_customer_days=c.max_sends_per_customer_days,
        budget=str(c.budget),
        expected_revenue=str(c.expected_revenue),
        tags=c.tags,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("/meta/types")
async def list_types(_: CurrentUser = Depends(get_current_user)) -> list[str]:
    return [t.value for t in CampaignType]


@router.get("/meta/channels")
async def list_channels(_: CurrentUser = Depends(get_current_user)) -> list[str]:
    return [c.value for c in Channel]


@router.get("/suggested-actions", response_model=list[SuggestedActionOut])
async def suggested_actions(
    user: CurrentUser = Depends(get_current_user),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
    rt: MarketingRuntime = Depends(_runtime),
) -> list[SuggestedActionOut]:
    shop_id = _require_shop_id(user)
    items = await list_suggested_action_counts(
        uow,
        shop_id,
        exclude_customer_ids=lambda ctype: rt.service.customers_in_recommendation_cooldown(
            shop_id, ctype
        ),
    )
    return [
        SuggestedActionOut(
            id=item.id,
            campaign_type=item.campaign_type,
            title=item.title,
            description=item.description,
            count=item.count,
            hint=(
                f"{item.count} customer{'s' if item.count != 1 else ''} ready"
                if item.count > 0
                else "No customers ready"
            ),
            custom_message=item.custom_message,
        )
        for item in items
    ]


@router.get("/metrics/summary")
async def metrics_summary(
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    shop_id = _require_shop_id(user)
    summary = await rt.service.analytics_summary(shop_id, exclude_demo=True)
    summary["monitor"] = rt.monitor.snapshot()
    return summary


@router.get("/calendar", response_model=list[CalendarEventOut])
async def campaign_calendar(
    start: date | None = None,
    end: date | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> list[CalendarEventOut]:
    shop_id = _require_shop_id(user)
    events = await rt.service.calendar(shop_id, start=start, end=end, exclude_demo=True)
    return [
        CalendarEventOut(
            campaign_id=e.campaign_id,
            name=e.name,
            campaign_type=e.campaign_type.value,
            status=e.status.value,
            day=e.day,
            channel=e.channel.value if e.channel else None,
            message_count=e.message_count,
        )
        for e in events
    ]


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(
    status_filter: str | None = Query(None, alias="status"),
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> list[CampaignOut]:
    st = CampaignStatus(status_filter) if status_filter else None
    return [
        _campaign_out(c)
        for c in await rt.service.list_campaigns(user.shop_id, status=st, exclude_demo=True)
    ]


@router.post("/campaigns", response_model=CampaignCreateOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
    uow: SqlAlchemyUnitOfWork = Depends(get_uow),
) -> CampaignCreateOut:
    shop_id = _require_shop_id(user)
    if body.use_demo_audience:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Demo audience is disabled; use real shop customers",
        )

    audience_payload = (
        [a.model_dump(mode="json") for a in body.audience] if body.audience else None
    )
    metadata = dict(body.metadata or {})

    if not audience_payload:
        members = await resolve_audience(
            uow,
            shop_id,
            body.campaign_type,
            tags=body.tags,
        )
        suppressed = await rt.service.customers_in_recommendation_cooldown(
            shop_id, body.campaign_type
        )
        members = rt.service.filter_audience_for_recommendations(members, suppressed)
        if not members:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="No matching customers found for this campaign",
            )
        audience_payload = audience_to_dicts(members)
        shop = await uow.shops.get_by_id(shop_id)
        if shop:
            metadata.setdefault("shop_name", shop.name)

    campaign = await rt.service.create_campaign(
        shop_id=shop_id,
        name=body.name,
        campaign_type=body.campaign_type,
        channels_allowed=[c.value for c in body.channels_allowed],
        audience=audience_payload,
        custom_message=body.custom_message,
        scheduled_start=body.scheduled_start,
        max_sends_per_customer_days=body.max_sends_per_customer_days,
        budget=body.budget,
        expected_revenue=body.expected_revenue,
        tags=body.tags,
        use_demo_audience=False,
        metadata=metadata,
        auto_schedule=body.auto_schedule,
    )
    rt.monitor.record_created(campaign.campaign_type.value)
    if body.auto_schedule:
        rt.monitor.record_scheduled()

    preview: dict[str, Any] | None = None
    if campaign.audience:
        try:
            preview = await rt.service.preview_ai(shop_id, campaign.id)
        except LookupError:
            preview = None

    base = _campaign_out(campaign)
    return CampaignCreateOut(**base.model_dump(), ai_preview=preview)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> CampaignOut:
    try:
        return _campaign_out(await rt.service.get_campaign(user.shop_id, campaign_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> CampaignOut:
    patch = body.model_dump(exclude_unset=True)
    if "channels_allowed" in patch and patch["channels_allowed"] is not None:
        patch["channels_allowed"] = [
            c.value if hasattr(c, "value") else c for c in patch["channels_allowed"]
        ]
    if "status" in patch and patch["status"] is not None:
        patch["status"] = patch["status"].value if hasattr(patch["status"], "value") else patch["status"]
    try:
        return _campaign_out(
            await rt.service.update_campaign(user.shop_id, campaign_id, patch)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/campaigns/{campaign_id}/schedule", response_model=CampaignOut)
async def schedule_campaign(
    campaign_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> CampaignOut:
    try:
        await rt.service.schedule_campaign(user.shop_id, campaign_id)
        rt.monitor.record_scheduled()
        return _campaign_out(await rt.service.get_campaign(user.shop_id, campaign_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/campaigns/{campaign_id}/process")
async def process_campaign_queue(
    campaign_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        shop_sent = await rt.service.process_campaign_now(user.shop_id, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for m in shop_sent:
        rt.monitor.record_sent(m.channel.value)
    return {"processed": len(shop_sent), "message_ids": [str(m.id) for m in shop_sent]}


@router.post("/queue/process")
async def process_queue(
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    shop_id = _require_shop_id(user)
    shop_sent = await rt.service.process_queue(shop_id=shop_id)
    for m in shop_sent:
        rt.monitor.record_sent(m.channel.value)
    return {"processed": len(shop_sent)}


@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageOut])
async def list_messages(
    campaign_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> list[MessageOut]:
    try:
        campaign = await rt.service.get_campaign(user.shop_id, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    names = _audience_name_map(campaign)
    messages = await rt.store.list_messages(user.shop_id, campaign_id)
    return [
        _message_out(m, customer_name=names.get(m.customer_id))
        for m in messages
    ]


@router.get("/campaigns/{campaign_id}/analytics", response_model=MetricsOut)
async def campaign_analytics(
    campaign_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> MetricsOut:
    try:
        m = await rt.service.get_metrics(user.shop_id, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MetricsOut(
        campaign_id=m.campaign_id,
        shop_id=m.shop_id,
        sent=m.sent,
        delivered=m.delivered,
        opened=m.opened,
        clicked=m.clicked,
        replied=m.replied,
        appointments=m.appointments,
        failed=m.failed,
        revenue=str(m.revenue),
        cost=str(m.cost),
        open_rate=m.open_rate,
        click_rate=m.click_rate,
        reply_rate=m.reply_rate,
        appointment_rate=m.appointment_rate,
        roi=m.roi,
    )


@router.get("/campaigns/{campaign_id}/ai-preview")
async def ai_preview(
    campaign_id: UUID,
    customer_id: UUID | None = None,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, Any]:
    try:
        return await rt.service.preview_ai(user.shop_id, campaign_id, customer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/messages/{message_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> None:
    shop_id = _require_shop_id(user)
    try:
        await rt.service.delete_message(shop_id, message_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/messages/bulk-delete")
async def bulk_delete_messages(
    body: BulkDeleteMessagesRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, int]:
    shop_id = _require_shop_id(user)
    deleted = await rt.service.delete_messages(shop_id, body.message_ids)
    return {"deleted": deleted}


@router.delete("/messages")
async def delete_all_messages(
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> dict[str, int]:
    shop_id = _require_shop_id(user)
    deleted = await rt.service.delete_all_messages(shop_id)
    return {"deleted": deleted}


@router.post("/messages/{message_id}/track", response_model=MessageOut)
async def track_message(
    message_id: UUID,
    body: TrackRequest,
    user: CurrentUser = Depends(get_current_user),
    rt: MarketingRuntime = Depends(_runtime),
) -> MessageOut:
    shop_id = _require_shop_id(user)
    try:
        m = await rt.service.track_event(
            shop_id,
            message_id,
            event=body.event,
            appointment_id=body.appointment_id,
            revenue=body.revenue,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    customer_name: str | None = None
    try:
        campaign = await rt.service.get_campaign(shop_id, m.campaign_id)
        customer_name = _audience_name_map(campaign).get(m.customer_id)
    except LookupError:
        pass
    return _message_out(m, customer_name=customer_name)
