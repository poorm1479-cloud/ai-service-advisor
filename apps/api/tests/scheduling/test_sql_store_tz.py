"""SQL appointment hydration must expose shop wall-clock starts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.scheduling.engines.availability import DEFAULT_SHOP_TZ
from app.scheduling.sql_store import _as_shop, _row_to_appointment


def test_as_shop_converts_utc_to_la_wall_clock():
    # 3:00 PM America/Los_Angeles (PDT) stored as UTC 22:00
    utc = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
    shop = _as_shop(utc)
    assert shop is not None
    assert shop.tzinfo is not None
    assert shop.astimezone(DEFAULT_SHOP_TZ).hour == 15
    assert shop.isoformat().startswith("2026-08-14T15:00:00")


def test_row_to_appointment_start_is_shop_wall_clock():
    shop_id = uuid4()
    appt_id = uuid4()
    utc_start = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
    utc_end = datetime(2026, 8, 14, 22, 30, tzinfo=timezone.utc)
    row = {
        "id": appt_id,
        "shop_id": shop_id,
        "start_at": utc_start,
        "end_at": utc_end,
        "status": "booked",
        "priority": "normal",
        "repair_type": "oil_change",
        "vehicle_type": "sedan",
        "estimated_duration_min": 30,
        "service_id": None,
        "customer_id": None,
        "vehicle_id": None,
        "mechanic_id": None,
        "bay_id": None,
        "walk_in_id": None,
        "source": "agent",
        "notes": None,
        "estimated_revenue": "0",
        "estimated_completion": utc_end,
        "wait_time_min": None,
        "created_at": utc_start,
        "metadata_json": None,
    }
    appt = _row_to_appointment(row)
    assert appt.start.hour == 15
    assert appt.end.hour == 15
    assert appt.start.minute == 0
    assert appt.end.minute == 30
    # Absolute instant preserved
    assert appt.start.astimezone(timezone.utc) == utc_start

