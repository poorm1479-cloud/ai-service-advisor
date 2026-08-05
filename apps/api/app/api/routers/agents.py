"""Agent pipeline HTTP surface — ingest normalized inbound messages."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agents.communication.models import RawInboundMessage
from app.agents.factory import AgentRuntime, build_agent_runtime
from app.api.deps import CurrentUser, get_current_user
from app.infrastructure.config import settings

router = APIRouter(prefix="/v1/agents", tags=["agents"])

_runtime: AgentRuntime | None = None


def get_agent_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        # Share scheduling intelligence with SMS/voice/calendar (not a private
        # InMemorySchedulingStore the Schedule UI never reads).
        from app.workflows.factory import get_workflow_runtime

        _runtime = build_agent_runtime(
            scheduling_store=get_workflow_runtime().coordinator.resolve_scheduling_agent_store()
        )
    return _runtime


class InboundMessageRequest(BaseModel):
    channel: str = Field(..., examples=["sms", "email", "phone", "facebook", "website_chat", "walk_in"])
    content: str
    sender_identifier: str | None = None
    subject: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineResponse(BaseModel):
    correlation_id: str
    success: bool
    escalate: bool
    owner_summary: str | None
    intent: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    stages: list[str]


@router.post("/inbound", response_model=PipelineResponse)
async def process_inbound(
    body: InboundMessageRequest,
    user: CurrentUser = Depends(get_current_user),
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> PipelineResponse:
    if not settings.agents_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agents disabled")

    result = await runtime.orchestrator.handle_incoming(
        shop_id=user.shop_id,
        message=RawInboundMessage(
            channel=body.channel,
            content=body.content,
            sender_identifier=body.sender_identifier,
            subject=body.subject,
            metadata=body.metadata,
        ),
        customer_id=body.customer_id,
        vehicle_id=body.vehicle_id,
    )

    intent = None
    intent_stage = result.stages.get("intent")
    if intent_stage and intent_stage.data:
        intent = intent_stage.data.intent.value

    return PipelineResponse(
        correlation_id=result.correlation_id,
        success=result.success,
        escalate=result.escalate,
        owner_summary=result.owner_summary,
        intent=intent,
        customer_id=result.context.customer_id,
        vehicle_id=result.context.vehicle_id,
        stages=list(result.stages.keys()),
    )


@router.get("/mcp/tools")
async def list_mcp_tools(
    user: CurrentUser = Depends(get_current_user),
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> dict[str, Any]:
    _ = user
    return {"tools": runtime.mcp.list_tools()}
