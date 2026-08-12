"""SMS Inbox API — conversations, timeline, reply preview, takeover."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, require_capabilities
from app.core.permissions.capabilities import StaffCapability
from app.domain.exceptions import ValidationError
from app.infrastructure.config import settings
from app.sms.factory import SmsRuntime
from app.sms.models import InboundSms
from app.sms.runtime import get_sms_runtime
from app.sms.store import InMemorySmsStore

router = APIRouter(prefix="/v1/sms", tags=["sms"])

_require_comms = require_capabilities(StaffCapability.CUSTOMER_COMMUNICATION)


def _runtime() -> SmsRuntime:
    return get_sms_runtime()


class ConversationOut(BaseModel):
    id: UUID
    shop_id: UUID
    customer_phone: str
    customer_id: UUID | None
    status: str
    last_intent: str | None
    owner_summary: str | None
    reply_preview: str | None
    escalate: bool
    escalation_reason: str | None
    human_takeover: bool
    last_message_at: datetime | None
    created_at: datetime | None


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    direction: str
    body: str
    intent: str | None
    twilio_sid: str | None
    created_at: datetime | None


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    timeline: list[dict[str, Any]]
    reply_preview: str | None
    owner_summary: str | None


class ManualReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1600)


class TakeoverRequest(BaseModel):
    enabled: bool = True


class SimulateInboundRequest(BaseModel):
    """Dev/test helper — simulate Twilio inbound without signature."""

    from_number: str
    body: str
    to_number: str | None = None


def _conv_out(c) -> ConversationOut:
    return ConversationOut(
        id=c.id,
        shop_id=c.shop_id,
        customer_phone=c.customer_phone,
        customer_id=c.customer_id,
        status=c.status,
        last_intent=c.last_intent,
        owner_summary=c.owner_summary,
        reply_preview=c.reply_preview,
        escalate=c.escalate,
        escalation_reason=c.escalation_reason,
        human_takeover=c.human_takeover,
        last_message_at=c.last_message_at,
        created_at=c.created_at,
    )


def _msg_out(m) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        direction=m.direction,
        body=m.body,
        intent=m.intent,
        twilio_sid=m.twilio_sid,
        created_at=m.created_at,
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    status_filter: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> list[ConversationOut]:
    items = await runtime.store.list_conversations(
        user.shop_id, status=status_filter, limit=limit
    )
    return [_conv_out(c) for c in items]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: UUID,
    include_timeline: bool = Query(False),
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> ConversationDetailOut:
    conv = await runtime.store.get_conversation(user.shop_id, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if include_timeline:
        messages, memory = await asyncio.gather(
            runtime.store.list_messages(user.shop_id, conversation_id),
            runtime.memory.load(
                shop_id=user.shop_id,
                customer_phone=conv.customer_phone,
                conversation_id=conv.id,
            ),
        )
        timeline = [
            {
                "role": t.role,
                "content": t.content,
                "intent": t.intent,
                "at": t.at.isoformat() if t.at else None,
            }
            for t in memory.turns
        ]
    else:
        # Inbox UI only needs messages — skip memory load on the hot path.
        messages = await runtime.store.list_messages(user.shop_id, conversation_id)
        timeline = []
    return ConversationDetailOut(
        conversation=_conv_out(conv),
        messages=[_msg_out(m) for m in messages],
        timeline=timeline,
        reply_preview=conv.reply_preview,
        owner_summary=conv.owner_summary,
    )


@router.post("/conversations/{conversation_id}/reply", response_model=MessageOut)
async def manual_reply(
    conversation_id: UUID,
    body: ManualReplyRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> MessageOut:
    try:
        msg = await runtime.service.send_manual_reply(
            shop_id=user.shop_id,
            conversation_id=conversation_id,
            body=body.body,
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _msg_out(msg)


@router.post("/conversations/{conversation_id}/takeover", response_model=ConversationOut)
async def human_takeover(
    conversation_id: UUID,
    body: TakeoverRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> ConversationOut:
    try:
        conv = await runtime.service.set_human_takeover(
            shop_id=user.shop_id,
            conversation_id=conversation_id,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _conv_out(conv)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> None:
    try:
        await runtime.service.delete_conversation(
            shop_id=user.shop_id,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/metrics")
async def sms_metrics(
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> dict[str, Any]:
    _ = user
    return {
        "metrics": runtime.monitor.snapshot(),
        "queue_depth": await runtime.queue.depth(),
        "provider": settings.twilio_provider,
    }


@router.post("/simulate", response_model=ConversationDetailOut)
async def simulate_inbound(
    body: SimulateInboundRequest,
    user: CurrentUser = Depends(_require_comms),
    runtime: SmsRuntime = Depends(_runtime),
) -> ConversationDetailOut:
    """Authenticated simulate endpoint for local/dev without Twilio."""
    if settings.environment == "production" and settings.twilio_provider == "twilio":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Simulate disabled in production")

    to_number = body.to_number or settings.twilio_from_number or "+15550001111"

    if isinstance(runtime.store, InMemorySmsStore):
        runtime.store.register_shop_number(user.shop_id, to_number)

    try:
        result = await runtime.service.process_inbound(
            shop_id=user.shop_id,
            inbound=InboundSms(
                from_number=body.from_number,
                to_number=to_number,
                body=body.body,
                message_sid=f"SM{uuid4().hex[:24]}",
            ),
        )
    except ValidationError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    messages = await runtime.store.list_messages(user.shop_id, result.conversation.id)
    memory = await runtime.memory.load(
        shop_id=user.shop_id,
        customer_phone=result.conversation.customer_phone,
        conversation_id=result.conversation.id,
    )
    return ConversationDetailOut(
        conversation=_conv_out(result.conversation),
        messages=[_msg_out(m) for m in messages],
        timeline=[
            {
                "role": t.role,
                "content": t.content,
                "intent": t.intent,
                "at": t.at.isoformat() if t.at else None,
            }
            for t in memory.turns
        ],
        reply_preview=result.reply.body,
        owner_summary=result.owner_summary,
    )
