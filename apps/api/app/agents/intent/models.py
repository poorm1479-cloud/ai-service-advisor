"""Intent agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CustomerIntent(str, Enum):
    BOOK_APPOINTMENT = "book_appointment"
    CHECK_AVAILABILITY = "check_availability"
    RESCHEDULE = "reschedule"
    CANCEL_APPOINTMENT = "cancel_appointment"
    ASK_REPAIR_STATUS = "ask_repair_status"
    PRICE_QUESTION = "price_question"
    MAINTENANCE_QUESTION = "maintenance_question"
    NEW_CUSTOMER = "new_customer"
    RETURNING_CUSTOMER = "returning_customer"
    COMPLAINT = "complaint"
    EMERGENCY = "emergency"
    OTHER = "other"


@dataclass(slots=True)
class IntentResult:
    intent: CustomerIntent
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    secondary_intents: list[CustomerIntent] = field(default_factory=list)
    is_emergency: bool = False
    is_complaint: bool = False
    raw_excerpt: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "secondary_intents": [i.value for i in self.secondary_intents],
            "is_emergency": self.is_emergency,
            "is_complaint": self.is_complaint,
            "raw_excerpt": self.raw_excerpt,
        }
