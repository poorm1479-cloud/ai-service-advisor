"""Shared helpers for shop-management API connectors."""

from __future__ import annotations

from typing import Any

import httpx

from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch
from app.import_engine.normalize import build_batch_from_sections


def sample_api_payload(provider: str) -> dict[str, list[dict[str, Any]]]:
    """Deterministic fixture used when credentials are missing or use_sample=true."""
    return {
        "customers": [
            {
                "external_id": f"{provider}-cust-1",
                "name": "Alex Rivera",
                "phone": "555-0100",
                "email": "alex@example.com",
                "address": "100 Main St",
            },
            {
                "external_id": f"{provider}-cust-2",
                "name": "Jordan Lee",
                "phone": "555-0101",
                "email": "jordan@example.com",
            },
        ],
        "vehicles": [
            {
                "external_id": f"{provider}-veh-1",
                "vin": "1HGCM82633A004352",
                "year": 2018,
                "make": "Honda",
                "model": "Accord",
                "mileage": 62000,
                "customer_external_id": f"{provider}-cust-1",
            }
        ],
        "repairs": [
            {
                "external_id": f"{provider}-rep-1",
                "vin": "1HGCM82633A004352",
                "service_type": "brakes",
                "description": "Front brake pads",
                "cost": 320.5,
                "mileage": 61000,
                "date": "2025-06-01",
                "recommendation": "Replace rotors within 6 months",
                "customer_external_id": f"{provider}-cust-1",
            }
        ],
        "invoices": [
            {
                "external_id": f"{provider}-inv-1",
                "invoice_number": f"{provider.upper()}-1001",
                "customer_external_id": f"{provider}-cust-1",
                "vin": "1HGCM82633A004352",
                "amount": 320.5,
                "tax": 25.64,
                "status": "paid",
                "date": "2025-06-01",
            }
        ],
        "estimates": [
            {
                "external_id": f"{provider}-est-1",
                "estimate_number": f"{provider.upper()}-E200",
                "customer_external_id": f"{provider}-cust-2",
                "amount": 180.0,
                "status": "open",
                "date": "2025-05-20",
            }
        ],
        "communications": [
            {
                "external_id": f"{provider}-com-1",
                "customer_external_id": f"{provider}-cust-1",
                "phone": "555-0100",
                "channel": "sms",
                "direction": "outbound",
                "message": "Your vehicle is ready for pickup.",
                "date": "2025-06-01T16:30:00",
            }
        ],
        "appointments": [
            {
                "external_id": f"{provider}-appt-1",
                "customer_external_id": f"{provider}-cust-1",
                "vin": "1HGCM82633A004352",
                "start": "2025-06-01T14:00:00",
                "end": "2025-06-01T16:00:00",
                "repair_type": "brakes",
                "status": "completed",
            }
        ],
        "recommendations": [
            {
                "external_id": f"{provider}-rec-1",
                "vin": "1HGCM82633A004352",
                "customer_external_id": f"{provider}-cust-1",
                "text": "Replace rotors within 6 months",
                "priority": "high",
            }
        ],
    }


async def fetch_or_sample(
    *,
    provider: str,
    source: ImportSource,
    base_url: str | None,
    api_key: str | None,
    path: str = "/export",
    use_sample: bool = False,
) -> NormalizedBatch:
    if use_sample or not api_key or not base_url:
        return build_batch_from_sections(sample_api_payload(provider), source=source)

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{base_url.rstrip('/')}{path}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if isinstance(data, dict) and any(k in data for k in ("customers", "vehicles")):
        sections = {k: v for k, v in data.items() if isinstance(v, list)}
    else:
        sections = sample_api_payload(provider)
        batch = build_batch_from_sections(sections, source=source)
        batch.warnings.append(f"{provider}: unexpected API shape; used normalized sample mapping")
        return batch
    return build_batch_from_sections(sections, source=source)
