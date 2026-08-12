"""Admin SMS/voice KPIs must read durable rows under FORCE RLS (survive API restart)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.admin.service import AdminConsoleService
from app.infrastructure.database import SessionLocal
from app.infrastructure.models import ShopModel, VoiceCallModel
from app.sms.runtime import get_sms_runtime, reset_sms_runtime
from app.voice.enums import VoiceCallStatus
from app.voice.runtime import get_voice_runtime, reset_voice_runtime


@pytest.mark.asyncio
async def test_admin_voice_snapshot_reads_db_under_rls() -> None:
    """Without app.sid_lookup, FORCE RLS hides voice_calls from unscoped SELECTs."""
    shop_id = uuid4()
    call_id = uuid4()
    now = datetime.now(timezone.utc)

    async with SessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.shop_id', :sid, true)"),
            {"sid": str(shop_id)},
        )
        session.add(
            ShopModel(
                id=shop_id,
                name=f"Voice Shop admin-rls-{shop_id.hex[:8]}",
                slug=f"admin-rls-voice-{shop_id.hex[:8]}",
                timezone="America/Los_Angeles",
            )
        )
        await session.flush()
        session.add(
            VoiceCallModel(
                id=call_id,
                shop_id=shop_id,
                twilio_call_sid=f"CA{call_id.hex}",
                caller_phone="+15550001111",
                called_phone="+15550002222",
                status=VoiceCallStatus.COMPLETED.value,
                created_at=now,
                started_at=now,
                ended_at=now,
            )
        )
        await session.commit()

    try:
        reset_voice_runtime()
        reset_sms_runtime()
        # Simulate post-restart: process-local monitor is empty.
        assert get_voice_runtime().monitor.snapshot()["calls_started"] == 0

        snap = await AdminConsoleService()._voice_snapshot()
        assert snap["source"] == "database"
        assert int(snap["calls_started"]) >= 1
        assert int(snap["calls_completed"]) >= 1
    finally:
        async with SessionLocal() as session:
            await session.execute(text("SELECT set_config('app.sid_lookup', '1', true)"))
            await session.execute(
                text("DELETE FROM voice_calls WHERE id = :id"),
                {"id": str(call_id)},
            )
            await session.execute(
                text("DELETE FROM shops WHERE id = :id"),
                {"id": str(shop_id)},
            )
            await session.commit()
        reset_voice_runtime()
        reset_sms_runtime()


@pytest.mark.asyncio
async def test_admin_sms_snapshot_uses_database_source() -> None:
    reset_sms_runtime()
    snap = await AdminConsoleService()._sms_snapshot()
    assert snap["source"] == "database"
    assert "inbound_received" in snap
    assert "outbound_sent" in snap
    # Monitor volume fields must not overwrite durable keys after restart.
    assert get_sms_runtime().monitor.snapshot()["inbound_received"] == 0
