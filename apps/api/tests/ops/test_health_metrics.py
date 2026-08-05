"""Phase 17 production health / metrics tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_liveness_and_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/live")
        assert live.status_code == 200
        assert live.json()["status"] == "alive"

        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["phase"] == "21-ai-learning-loop"


@pytest.mark.asyncio
async def test_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generate a request so counters exist
        await client.get("/health")
        metrics = await client.get("/metrics")
        assert metrics.status_code == 200
        body = metrics.text
        assert "asa_http_requests_total" in body
        assert "asa_app_info" in body


def test_routes_registered():
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/live" in paths
    assert "/ready" in paths
    assert "/metrics" in paths
