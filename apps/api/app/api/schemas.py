from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.domain.enums import CommunicationChannel, CommunicationDirection, UserRole, WalkInStatus


class SendOtpRequest(BaseModel):
    channel: str = Field(default="phone", pattern=r"^(phone|email)$")
    phone: str | None = Field(default=None, min_length=8, max_length=32)
    email: EmailStr | None = None
    purpose: str = Field(default="register", pattern=r"^(register|login|invite)$")

    @model_validator(mode="after")
    def require_channel_target(self) -> "SendOtpRequest":
        if self.channel == "phone" and not self.phone:
            raise ValueError("phone is required for phone channel")
        if self.channel == "email" and not self.email:
            raise ValueError("email is required for email channel")
        return self


class SendOtpResponse(BaseModel):
    channel: str
    target: str
    purpose: str
    expires_in: int
    resend_after: int
    challenge_id: str
    phone: str | None = None
    email: str | None = None
    dev_code: str | None = None
    message: str = "Verification code sent"


class VerifyOtpRequest(BaseModel):
    channel: str = Field(default="phone", pattern=r"^(phone|email)$")
    phone: str | None = Field(default=None, min_length=8, max_length=32)
    email: EmailStr | None = None
    code: str = Field(min_length=4, max_length=12)
    purpose: str = Field(default="register", pattern=r"^(register|login|invite)$")


class VerifyOtpResponse(BaseModel):
    ok: bool = True
    channel: str
    target: str
    purpose: str


class RegisterShopRequest(BaseModel):
    shop_name: str = Field(min_length=2, max_length=255)
    # Optional legacy field — server auto-generates slug from shop_name when omitted.
    shop_slug: str | None = Field(
        default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$"
    )
    auth_method: str = Field(default="phone", pattern=r"^(phone|email)$")
    otp_code: str | None = Field(default=None, min_length=4, max_length=12)
    owner_full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    owner_phone: str | None = Field(default=None, min_length=8, max_length=32)
    owner_email: EmailStr | None = None
    timezone: str = Field(default="America/Los_Angeles", max_length=64)

    @model_validator(mode="after")
    def require_primary_identifier(self) -> "RegisterShopRequest":
        if self.auth_method == "phone" and not self.owner_phone:
            raise ValueError("owner_phone is required when auth_method=phone")
        if self.auth_method == "email" and not self.owner_email:
            raise ValueError("owner_email is required when auth_method=email")
        return self


class LoginRequest(BaseModel):
    password: str
    shop_name: str | None = Field(default=None, min_length=2, max_length=255)
    # Optional legacy field — prefer shop_name for new clients.
    shop_slug: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, min_length=8, max_length=32)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def require_phone_or_email(self) -> "LoginRequest":
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        if not (self.shop_name and self.shop_name.strip()) and not (
            self.shop_slug and self.shop_slug.strip()
        ):
            raise ValueError("shop_name is required")
        return self


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def require_password(cls, value: str) -> str:
        if not value:
            raise ValueError("password is required")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class TokenResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 0
    user_id: UUID
    shop_id: UUID | None = None
    role: str
    capabilities: list[str] = Field(default_factory=list)
    primary_auth_method: str = "phone"
    username: str | None = None
    phone: str | None = None
    email: str | None = None
    full_name: str
    shop_name: str = ""
    shop_slug: str = ""
    account_type: str = "shop"
    mfa_required: bool = False
    mfa_token: str | None = None


class MeResponse(BaseModel):
    user_id: UUID
    primary_auth_method: str = "phone"
    username: str | None = None
    phone: str | None = None
    email: str | None = None
    full_name: str
    shop_id: UUID
    shop_name: str
    shop_slug: str
    role: UserRole
    capabilities: list[str] = Field(default_factory=list)
    phone_verified: bool = False
    email_verified: bool = False
    mfa_enabled: bool = False


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)

    @field_validator("phone", "email", "address", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)

    @field_validator("phone", "email", "address", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CustomerOut(BaseModel):
    id: UUID
    shop_id: UUID
    name: str
    phone: str | None
    email: str | None
    address: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VehicleCreate(BaseModel):
    vin: str = Field(min_length=17, max_length=17)
    license_plate: str | None = Field(default=None, max_length=32)
    year: int = Field(ge=1900, le=2100)
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    mileage: int = Field(ge=0, le=3_000_000)

    @field_validator("vin")
    @classmethod
    def vin_upper(cls, value: str) -> str:
        return value.strip().upper()


class VehicleUpdate(BaseModel):
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    license_plate: str | None = Field(default=None, max_length=32)
    year: int | None = Field(default=None, ge=1900, le=2100)
    make: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    mileage: int | None = Field(default=None, ge=0, le=3_000_000)

    @field_validator("vin")
    @classmethod
    def vin_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @field_validator("license_plate", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class VehicleOut(BaseModel):
    id: UUID
    shop_id: UUID
    customer_id: UUID | None
    vin: str
    license_plate: str | None
    year: int
    make: str
    model: str
    mileage: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RepairHistoryCreate(BaseModel):
    service_type: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    recommendation: str | None = Field(default=None, max_length=5000)
    # Optional service/repair date (stored as created_at). Defaults to now when omitted.
    created_at: datetime | None = None


class RepairHistoryOut(BaseModel):
    id: UUID
    shop_id: UUID
    customer_id: UUID | None
    vehicle_id: UUID
    service_type: str
    description: str
    cost: Decimal
    recommendation: str | None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CommunicationCreate(BaseModel):
    channel: CommunicationChannel
    message: str = Field(min_length=1, max_length=10000)
    direction: CommunicationDirection


class CommunicationOut(BaseModel):
    id: UUID
    shop_id: UUID
    customer_id: UUID
    channel: CommunicationChannel
    message: str
    direction: CommunicationDirection
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class VehicleDetailOut(BaseModel):
    vehicle: VehicleOut
    repair_history: list[RepairHistoryOut]


class VinDecodedOut(BaseModel):
    vin: str
    year: int
    make: str
    model: str
    body_class: str | None = None
    source: str = "nhtsa"


class VinAssistOut(BaseModel):
    vin: str
    existing: VehicleOut | None = None
    decoded: VinDecodedOut | None = None
    message: str | None = None


class VehicleMatchAssistOut(BaseModel):
    existing: VehicleOut | None = None
    match_type: str | None = None
    message: str | None = None


class CustomerDetailOut(BaseModel):
    customer: CustomerOut
    vehicles: list[VehicleOut]
    communications: list[CommunicationOut]
    repair_history: list[RepairHistoryOut] = []


class CustomerDirectoryItemOut(BaseModel):
    customer: CustomerOut
    vehicles: list[VehicleOut]
    last_service: RepairHistoryOut | None = None


class WalkInCreate(BaseModel):
    vin: str = Field(min_length=17, max_length=17)
    license_plate: str | None = Field(default=None, max_length=32)
    year: int = Field(ge=1900, le=2100)
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    mileage: int = Field(ge=0, le=3_000_000)
    complaint: str = Field(min_length=1, max_length=5000)
    arrived_at: datetime | None = None

    @field_validator("vin")
    @classmethod
    def vin_upper(cls, value: str) -> str:
        return value.strip().upper()


class WalkInConvertCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=500)


class WalkInAttachVehicle(BaseModel):
    vehicle_id: UUID | None = None
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    license_plate: str | None = Field(default=None, max_length=32)
    year: int | None = Field(default=None, ge=1900, le=2100)
    make: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    mileage: int | None = Field(default=None, ge=0, le=3_000_000)

    @field_validator("vin")
    @classmethod
    def vin_upper(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class WalkInVisitOut(BaseModel):
    id: UUID
    shop_id: UUID
    vehicle_id: UUID
    customer_id: UUID | None
    complaint: str
    status: WalkInStatus
    arrived_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class WalkInDetailOut(BaseModel):
    visit: WalkInVisitOut
    vehicle: VehicleOut
    customer: CustomerOut | None
    repair_history: list[RepairHistoryOut]
