"""Communication agent models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class InboundChannel(str, Enum):
    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"
    FACEBOOK = "facebook"
    WEBSITE_CHAT = "website_chat"
    WALK_IN = "walk_in"


@dataclass(slots=True)
class RawInboundMessage:
    channel: str
    content: str
    sender_identifier: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedMessage:
    channel: str
    direction: str
    body: str
    sender: str | None
    recipient: str | None
    subject: str | None
    received_at: datetime | None
    language: str
    metadata: dict[str, Any]
