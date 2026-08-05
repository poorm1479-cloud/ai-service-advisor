"""MCP Integration Hub enums."""

from __future__ import annotations

from enum import StrEnum


class IntegrationProvider(StrEnum):
    TEKMETRIC = "tekmetric"
    SHOPMONKEY = "shopmonkey"
    AUTOLEAP = "autoleap"
    MITCHELL = "mitchell"
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_BUSINESS = "google_business"
    TWILIO = "twilio"
    STRIPE = "stripe"
    FACEBOOK = "facebook"
    EMAIL = "email"
    FUTURE = "future"


class AuthMethod(StrEnum):
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    BEARER = "bearer"
    WEBHOOK_SECRET = "webhook_secret"
    NONE = "none"


class ConnectionStatus(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    REVOKED = "revoked"


class IntegrationCategory(StrEnum):
    PMS = "pms"
    CALENDAR = "calendar"
    BUSINESS = "business"
    COMMUNICATIONS = "communications"
    PAYMENTS = "payments"
    SOCIAL = "social"
    MESSAGING = "messaging"
    EXTENSIBILITY = "extensibility"


class PermissionAction(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    INVOKE = "invoke"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class InvokeStatus(StrEnum):
    SUCCESS = "success"
    RETRYING = "retrying"
    FAILED = "failed"
    DENIED = "denied"
