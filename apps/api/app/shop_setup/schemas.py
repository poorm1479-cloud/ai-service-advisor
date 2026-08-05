"""Pydantic schemas for shop setup + service catalog."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class BusinessHoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: str = Field(min_length=4, max_length=8)
    close_time: str = Field(min_length=4, max_length=8)
    # Required — a default of False would silently open days when clients omit the field.
    closed: bool

    @field_validator("open_time", "close_time")
    @classmethod
    def normalize_time(cls, value: str) -> str:
        raw = value.strip()
        parts = raw.split(":")
        # Accept HH:MM or HH:MM:SS (browsers / time.isoformat()).
        if len(parts) not in (2, 3):
            raise ValueError("Time must be HH:MM")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError("Time must be HH:MM") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Invalid time")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("closed", mode="before")
    @classmethod
    def coerce_closed(cls, value: object) -> bool:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", ""}:
                return False
        return bool(value)


class BusinessHoursOut(BusinessHoursIn):
    pass


class ShopProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=64)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=64)
    website: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ShopProfileOut(BaseModel):
    shop_id: UUID
    name: str
    slug: str
    timezone: str
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str = "US"
    website: str | None = None
    description: str | None = None
    setup_completed: bool = False
    setup_completed_at: datetime | None = None


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    duration_minutes: int = Field(ge=5, le=24 * 60)
    price: Decimal = Field(ge=0)
    skill: str = Field(min_length=1, max_length=64)
    bay: str = Field(min_length=1, max_length=64)
    active: bool = True
    sort_order: int | None = Field(default=None, ge=0)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    duration_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    price: Decimal | None = Field(default=None, ge=0)
    skill: str | None = Field(default=None, min_length=1, max_length=64)
    bay: str | None = Field(default=None, min_length=1, max_length=64)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class ServiceOut(BaseModel):
    id: UUID
    shop_id: UUID
    name: str
    category: str
    duration_minutes: int
    price: Decimal
    skill: str
    bay: str
    active: bool
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SetupStatusOut(BaseModel):
    setup_completed: bool
    has_shop_info: bool
    has_business_hours: bool
    has_services: bool
    service_count: int
    missing: list[str] = Field(default_factory=list)


class SetupStateOut(BaseModel):
    status: SetupStatusOut
    profile: ShopProfileOut
    business_hours: list[BusinessHoursOut]
    services: list[ServiceOut]
    meta: dict


class CompleteSetupRequest(BaseModel):
    profile: ShopProfileIn
    business_hours: list[BusinessHoursIn] = Field(min_length=7, max_length=7)
    services: list[ServiceIn] = Field(min_length=1)


class UpdateShopSettingsRequest(BaseModel):
    """Editable shop settings (profile + optional hours)."""

    profile: ShopProfileIn | None = None
    business_hours: list[BusinessHoursIn] | None = Field(default=None, min_length=7, max_length=7)


class PhoneSchedulingCatalogOut(BaseModel):
    """Structured payload for AI phone scheduling agents."""

    shop_id: UUID
    shop_name: str
    shop_slug: str
    timezone: str
    phone: str | None = None
    address: str | None = None
    business_hours: list[BusinessHoursOut]
    services: list[ServiceOut]
    bookable_service_count: int
