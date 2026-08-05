"""Analytics enums."""

from __future__ import annotations

from enum import StrEnum


class KpiId(StrEnum):
    REVENUE = "revenue"
    RETENTION = "retention"
    AVERAGE_REPAIR_ORDER = "average_repair_order"
    CUSTOMER_LIFETIME_VALUE = "customer_lifetime_value"
    APPOINTMENT_CONVERSION = "appointment_conversion"
    MARKETING_ROI = "marketing_roi"
    MECHANIC_PRODUCTIVITY = "mechanic_productivity"
    AI_SUCCESS_RATE = "ai_success_rate"


class ReportType(StrEnum):
    EXECUTIVE_SUMMARY = "executive_summary"
    REVENUE = "revenue"
    RETENTION = "retention"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    AI_PERFORMANCE = "ai_performance"
    FULL = "full"


class ExportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


class TrendDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class PeriodGranularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
