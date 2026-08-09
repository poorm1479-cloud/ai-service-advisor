from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import CommunicationChannel, CommunicationDirection, UserRole, WalkInStatus


@dataclass(slots=True)
class Shop:
    id: UUID
    name: str
    slug: str
    timezone: str
    ai_paused: bool = False
    created_at: datetime | None = None


@dataclass(slots=True)
class User:
    id: UUID
    full_name: str
    password_hash: str
    username: str | None = None
    phone: str | None = None
    email: str | None = None
    phone_verified: bool = False
    email_verified: bool = False
    primary_auth_method: str = "phone"
    account_type: str = "shop"
    mfa_enabled: bool = False
    mfa_secret: str | None = None
    mfa_backup_codes_json: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


@dataclass(slots=True)
class ShopMembership:
    id: UUID
    shop_id: UUID
    user_id: UUID
    role: UserRole
    capabilities: list[str] | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class RefreshToken:
    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    shop_id: UUID | None = None
    revoked_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class Customer:
    id: UUID
    shop_id: UUID
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class Vehicle:
    id: UUID
    shop_id: UUID
    vin: str
    year: int
    make: str
    model: str
    mileage: int
    customer_id: UUID | None = None
    license_plate: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class RepairHistory:
    id: UUID
    shop_id: UUID
    vehicle_id: UUID
    service_type: str
    description: str
    cost: Decimal
    customer_id: UUID | None = None
    recommendation: str | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class CommunicationHistory:
    id: UUID
    shop_id: UUID
    customer_id: UUID
    channel: CommunicationChannel
    message: str
    direction: CommunicationDirection
    created_at: datetime | None = None


@dataclass(slots=True)
class WalkInVisit:
    id: UUID
    shop_id: UUID
    vehicle_id: UUID
    complaint: str
    status: WalkInStatus
    customer_id: UUID | None = None
    arrived_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class VoiceNote:
    id: UUID
    shop_id: UUID
    employee_id: UUID
    audio_url: str
    transcript: str | None = None
    created_at: datetime | None = None
