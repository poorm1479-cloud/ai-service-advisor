"""Conversation AI enrichment — wraps pipeline signals (no model rewrite)."""

from __future__ import annotations

from typing import Any

from app.plugins.conversation.models import Conversation, ConversationAiInsights


class ConversationIntelligenceService:
    """Derive Conversation AI insights from inbound text + optional pipeline metadata."""

    def enrich(
        self,
        conversation: Conversation,
        *,
        text: str | None = None,
        intent: str | None = None,
        confidence: float | None = None,
        escalate: bool = False,
        owner_summary: str | None = None,
        suggested_reply: str | None = None,
        revenue_opportunity: float | None = None,
        risk_score: float | None = None,
        priority: str | None = None,
    ) -> ConversationAiInsights:
        body = (text or "").lower()
        sentiment = self._sentiment(body)
        urgency = self._urgency(body, intent=intent, escalate=escalate, priority=priority)
        service = self._suggested_service(body, intent=intent)
        appointment = None
        if intent in {"book_appointment", "reschedule", "schedule"} or "appointment" in body:
            appointment = "Offer next available appointment slot"
        ai = ConversationAiInsights(
            summary=owner_summary
            or conversation.ai.summary
            or (f"Customer via {conversation.channel}: {(text or '')[:160]}"),
            intent=intent or conversation.ai.intent,
            sentiment=sentiment,
            urgency_score=urgency,
            suggested_reply=suggested_reply or conversation.ai.suggested_reply,
            suggested_service=service,
            suggested_appointment=appointment,
            risk_score=float(
                risk_score
                if risk_score is not None
                else (0.8 if escalate or sentiment == "negative" else 0.2)
            ),
            revenue_opportunity=float(revenue_opportunity or 0.0),
            confidence=float(confidence or conversation.ai.confidence or 0.0),
            highlights=list(conversation.ai.highlights),
            action_items=list(conversation.ai.action_items),
        )
        return ai

    def summarize(self, conversation: Conversation) -> dict[str, Any]:
        recent = conversation.messages[-5:] if conversation.messages else []
        return {
            "conversation_id": str(conversation.id),
            "status": conversation.status,
            "channel": conversation.channel,
            "channel_history": list(conversation.channel_history),
            "priority": conversation.priority,
            "customer_id": str(conversation.customer_id) if conversation.customer_id else None,
            "vehicle_id": str(conversation.vehicle_id) if conversation.vehicle_id else None,
            "current_workflow": conversation.current_workflow,
            "assigned_advisor": conversation.assigned_advisor,
            "message_count": len(conversation.messages),
            "recent_messages": [
                {"sender": m.sender, "content": m.content[:200], "channel": m.channel}
                for m in recent
            ],
            "ai": {
                "summary": conversation.ai.summary,
                "intent": conversation.ai.intent,
                "sentiment": conversation.ai.sentiment,
                "urgency_score": conversation.ai.urgency_score,
                "suggested_reply": conversation.ai.suggested_reply,
                "suggested_service": conversation.ai.suggested_service,
                "suggested_appointment": conversation.ai.suggested_appointment,
                "risk_score": conversation.ai.risk_score,
                "revenue_opportunity": conversation.ai.revenue_opportunity,
                "confidence": conversation.ai.confidence,
                "highlights": list(conversation.ai.highlights),
                "action_items": list(conversation.ai.action_items),
            },
            "workflow_history_count": len(conversation.workflow_history),
            "ai_decisions_count": len(conversation.ai_decisions),
        }

    def _sentiment(self, body: str) -> str:
        negative = ("angry", "upset", "terrible", "lawsuit", "refund", "complaint", "worst")
        positive = ("thanks", "great", "appreciate", "perfect", "love")
        if any(w in body for w in negative):
            return "negative"
        if any(w in body for w in positive):
            return "positive"
        return "neutral"

    def _urgency(
        self,
        body: str,
        *,
        intent: str | None,
        escalate: bool,
        priority: str | None,
    ) -> float:
        if escalate or priority == "urgent":
            return 0.95
        if intent in {"emergency", "breakdown"} or any(
            w in body for w in ("tow", "stranded", "smoke", "fire", "accident")
        ):
            return 0.9
        if priority == "high" or "asap" in body or "urgent" in body:
            return 0.75
        return 0.35

    def _suggested_service(self, body: str, *, intent: str | None) -> str | None:
        mapping = [
            (("oil",), "oil_change"),
            (("brake",), "brakes"),
            (("tire", "tyre"), "tires"),
            (("battery",), "battery"),
            (("ac ", "a/c", "air condition"), "ac_service"),
            (("inspect",), "inspection"),
        ]
        for keys, service in mapping:
            if any(k in body for k in keys):
                return service
        if intent and intent not in {"unknown", "greeting", "other"}:
            return intent
        return None
