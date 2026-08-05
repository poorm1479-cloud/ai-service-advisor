"""Marketing automation enumerations."""

from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    VOICE = "voice"


class CampaignType(StrEnum):
    MAINTENANCE_REMINDER = "maintenance_reminder"
    DECLINED_ESTIMATE = "declined_estimate"
    THANK_YOU = "thank_you"
    REVIEW_REQUEST = "review_request"
    SEASONAL_PROMOTION = "seasonal_promotion"
    RECALL_NOTICE = "recall_notice"
    BIRTHDAY = "birthday"
    INACTIVE_CUSTOMER = "inactive_customer"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MessageStatus(StrEnum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    REPLIED = "replied"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class QueueItemState(StrEnum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXHAUSTED = "exhausted"
