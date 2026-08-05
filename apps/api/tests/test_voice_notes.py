"""Mechanic voice notes — STT + AI extraction → RepairHistory."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

VALID_VIN = "1HGCM82633A123456"
SAMPLE_TRANSCRIPT = (
    "2019 Honda Accord oil change completed. "
    "Brake pads are 30 percent. "
    "Recommend replacement next visit. "
    "Mileage 82000."
)


@pytest.fixture
async def require_db():
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://asa:asa@localhost:5432/ai_service_advisor",
    )
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not available")
    finally:
        await engine.dispose()


@pytest.fixture
async def client(require_db, tmp_path, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "heuristic")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path / "audio"))
    # Reload settings/factory pick up env — settings already loaded; patch module settings
    from app.infrastructure import config
    from app.infrastructure.ai import factory

    config.settings.audio_storage_dir = str(tmp_path / "audio")
    config.settings.ai_provider = "heuristic"
    factory.settings.audio_storage_dir = str(tmp_path / "audio")

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_with_vehicle(client: AsyncClient, suffix: str) -> tuple[dict, str]:
    from tests.auth_helpers import register_shop_via_otp

    token = await register_shop_via_otp(
        client,
        suffix=suffix.replace("-", "")[:8],
        shop_name=f"Voice Shop {suffix}",
        shop_slug=f"voice-{suffix}",
        owner_full_name="Voice Owner",
        email=f"voice-{suffix}@example.com",
    )
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    customer = await client.post(
        "/v1/customers",
        headers=headers,
        json={"name": "Voice Customer"},
    )
    assert customer.status_code == 201, customer.text

    vehicle = await client.post(
        f"/v1/customers/{customer.json()['id']}/vehicles",
        headers=headers,
        json={
            "vin": VALID_VIN,
            "year": 2019,
            "make": "Honda",
            "model": "Accord",
            "mileage": 70000,
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    return token, vehicle.json()["id"]


async def test_voice_note_creates_repair_history(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    token, vehicle_id = await _register_with_vehicle(client, suffix)
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    files = {
        "audio": ("note.txt", SAMPLE_TRANSCRIPT.encode("utf-8"), "text/plain"),
    }
    data = {"vehicle_id": vehicle_id}
    res = await client.post("/v1/voice-notes", headers=headers, data=data, files=files)
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["voice_note"]["employee_id"] == token["user_id"]
    assert body["voice_note"]["transcript"]
    assert "oil change" in body["voice_note"]["transcript"].lower()
    assert body["extraction"]["service"] == "Oil Change"
    assert body["extraction"]["mileage"] == 82000
    assert body["extraction"]["recommendation"]
    assert body["repair_history"]["service_type"] == "Oil Change"
    assert body["vehicle"]["mileage"] == 82000

    history = await client.get(f"/v1/vehicles/{vehicle_id}/history", headers=headers)
    assert history.status_code == 200
    assert any(h["id"] == body["repair_history"]["id"] for h in history.json())


async def test_voice_note_shop_isolation(client: AsyncClient):
    from tests.auth_helpers import register_shop_via_otp

    suffix = uuid.uuid4().hex[:8]
    token_a, vehicle_id = await _register_with_vehicle(client, f"a{suffix[:6]}")
    token_b = await register_shop_via_otp(
        client,
        suffix=f"b{suffix[:6]}",
        shop_name=f"Other {suffix}",
        shop_slug=f"other-{suffix}",
        email=f"other-{suffix}@example.com",
    )

    headers_a = {"Authorization": f"Bearer {token_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {token_b['access_token']}"}

    created = await client.post(
        "/v1/voice-notes",
        headers=headers_a,
        data={"vehicle_id": vehicle_id},
        files={"audio": ("note.txt", SAMPLE_TRANSCRIPT.encode("utf-8"), "text/plain")},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["voice_note"]["id"]

    list_b = await client.get("/v1/voice-notes", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    get_b = await client.get(f"/v1/voice-notes/{note_id}", headers=headers_b)
    assert get_b.status_code == 404
