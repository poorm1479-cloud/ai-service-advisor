"""VIN decode helpers — NHTSA VPIC + shop vehicle lookup."""

from __future__ import annotations

from typing import Any

import httpx

from app.application.crm_service import _normalize_vin
from app.domain.exceptions import ValidationError

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


async def decode_vin_nhtsa(vin: str) -> dict[str, Any] | None:
    """Return year/make/model from NHTSA, or None if unavailable."""
    try:
        normalized = _normalize_vin(vin)
    except ValidationError:
        raise

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(NHTSA_URL.format(vin=normalized))
            res.raise_for_status()
            payload = res.json()
    except Exception:
        return None

    results = payload.get("Results") or []
    if not results:
        return None
    row = results[0]
    error_code = str(row.get("ErrorCode") or "")
    # 0 = success; some partial decodes still useful
    if error_code and error_code.split(",")[0].strip() not in {"0", "1", "6", "7", "8", "11"}:
        # still try if make/year present
        pass

    year_raw = (row.get("ModelYear") or "").strip()
    make = (row.get("Make") or "").strip().title()
    model = (row.get("Model") or "").strip()
    if not year_raw or not make:
        return None
    try:
        year = int(year_raw)
    except ValueError:
        return None

    return {
        "vin": normalized,
        "year": year,
        "make": make,
        "model": model or "Unknown",
        "body_class": (row.get("BodyClass") or "").strip() or None,
        "source": "nhtsa",
    }
