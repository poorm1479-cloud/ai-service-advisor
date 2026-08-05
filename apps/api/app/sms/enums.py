"""SMS domain enums."""

from enum import Enum


class SmsConversationStatus(str, Enum):
    ACTIVE = "active"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_HUMAN = "waiting_human"
    ESCALATED = "escalated"
    CLOSED = "closed"


class SmsMessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    SYSTEM = "system"


class SmsJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"
