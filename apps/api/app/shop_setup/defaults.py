"""Default hours, categories, and starter service templates."""

from __future__ import annotations

from decimal import Decimal

SERVICE_CATEGORIES: list[str] = [
    "maintenance",
    "brakes",
    "tires",
    "electrical",
    "engine",
    "transmission",
    "diagnostic",
    "other",
]

SERVICE_SKILLS: list[str] = [
    "oil_change",
    "brakes",
    "tires",
    "alignment",
    "battery",
    "fluids",
    "diagnostic",
    "general",
]

BAY_TYPES: list[str] = [
    "general",
    "alignment",
    "quick_service",
    "heavy",
]

WEEKDAY_LABELS: dict[int, str] = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def default_business_hours() -> list[dict]:
    """Mon–Fri 08:00–17:00, weekend closed."""
    hours: list[dict] = []
    for day in range(7):
        closed = day >= 5
        hours.append(
            {
                "weekday": day,
                "open_time": "08:00",
                "close_time": "17:00",
                "closed": closed,
            }
        )
    return hours


# Starter catalog shown in the wizard (shop edits before saving).
STARTER_SERVICES: list[dict] = [
    {
        "name": "Oil Change",
        "category": "maintenance",
        "duration_minutes": 30,
        "price": Decimal("49.99"),
        "skill": "oil_change",
        "bay": "quick_service",
        "active": True,
    },
    {
        "name": "Brake Inspection",
        "category": "brakes",
        "duration_minutes": 45,
        "price": Decimal("89.00"),
        "skill": "brakes",
        "bay": "general",
        "active": True,
    },
    {
        "name": "Brake Repair",
        "category": "brakes",
        "duration_minutes": 120,
        "price": Decimal("320.00"),
        "skill": "brakes",
        "bay": "general",
        "active": True,
    },
    {
        "name": "Tire Rotation",
        "category": "tires",
        "duration_minutes": 40,
        "price": Decimal("39.99"),
        "skill": "tires",
        "bay": "general",
        "active": True,
    },
]
