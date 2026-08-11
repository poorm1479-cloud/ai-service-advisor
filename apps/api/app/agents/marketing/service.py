"""Marketing Agent — pure Decision Layer (compose messages; do not dispatch)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base.agent import Agent, AgentContext, AgentResult
from app.agents.base.logging import get_agent_logger
from app.agents.decisions.types import MarketingDecision
from app.agents.marketing.interfaces import MarketingDispatcherPort
from app.agents.marketing.models import (
    MarketingActionResult,
    MarketingActionType,
    MarketingRequest,
)

_TEMPLATES = {
    MarketingActionType.SMS_CAMPAIGN: (
        "Hi{name}, it's {shop} — whenever you're ready for your next service, "
        "just reply here or book online. We're happy to help."
    ),
    MarketingActionType.EMAIL_CAMPAIGN: (
        "Hi{name}, thanks for trusting {shop}. Here's a simple tip that helps "
        "a lot of drivers like you: {tip}"
    ),
    MarketingActionType.REVIEW_REQUEST: (
        "Hi{name}, hope everything's going well since your visit to {shop}! "
        "If you have a moment, we'd love to hear how we did: {review_link}"
    ),
    MarketingActionType.THANK_YOU: (
        "Thank you{name} for choosing {shop}. It meant a lot having you in — "
        "we're glad we could help with your vehicle."
    ),
    MarketingActionType.MAINTENANCE_REMINDER: (
        "Hi{name}, just a friendly heads-up — your {service} is coming up "
        "(around {due_mileage} miles). Reply BOOK when you'd like us to save a spot."
    ),
}


class LoggingMarketingDispatcher:
    """Default dispatcher — used only by Workflow DecisionExecutor."""

    def __init__(self) -> None:
        self._logger = get_agent_logger("marketing.dispatcher")
        self.sent: list[MarketingActionResult] = []

    async def dispatch(self, action: MarketingActionResult) -> MarketingActionResult:
        self._logger.info(
            "marketing.dispatch channel=%s type=%s",
            action.channel,
            action.action_type,
        )
        action.dispatched = True
        self.sent.append(action)
        return action


class MarketingAgent(Agent[MarketingRequest, MarketingActionResult]):
    """Decision-only marketing AI — composes content; Workflow dispatches."""

    name = "marketing"

    def __init__(self, dispatcher: MarketingDispatcherPort | None = None) -> None:
        super().__init__()
        # Dispatcher retained for DI into DecisionPorts — agent never calls it.
        self._dispatcher = dispatcher or LoggingMarketingDispatcher()

    @property
    def dispatcher(self) -> MarketingDispatcherPort:
        return self._dispatcher

    async def handle(
        self, payload: MarketingRequest, context: AgentContext
    ) -> AgentResult[MarketingActionResult]:
        return await self.execute(payload, context)

    async def execute(
        self, request: MarketingRequest, context: AgentContext
    ) -> AgentResult[MarketingActionResult]:
        template_key = request.action_type
        template = request.template or _TEMPLATES[template_key]
        ctx = {
            "name": "",
            "shop": "our shop",
            "tip": "check tire pressure monthly",
            "review_link": "https://reviews.example.com",
            "service": "oil change",
            "due_mileage": "—",
            **request.context,
        }
        if ctx.get("name"):
            ctx["name"] = f" {ctx['name']}"
        body = template.format_map(_SafeDict(ctx))
        scheduled_at = request.scheduled_at or datetime.now(timezone.utc)

        decision = MarketingDecision(
            action_type=request.action_type.value,
            channel=request.channel,
            customer_id=request.customer_id or context.customer_id,
            template=template,
            body=body,
            context=dict(request.context),
            scheduled_at=scheduled_at,
            rationale=f"Compose {request.action_type.value} marketing message",
        )

        action = MarketingActionResult(
            action_type=request.action_type.value,
            channel=request.channel,
            customer_id=request.customer_id or context.customer_id,
            template=template,
            body=body,
            scheduled_at=scheduled_at,
            dispatched=False,
            payload=dict(request.context),
            decision=decision,
        )
        return AgentResult.ok(action)


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""
