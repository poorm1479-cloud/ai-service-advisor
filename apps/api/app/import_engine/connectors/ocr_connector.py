"""OCR text extraction for repair documents (VIN, mileage, customer, etc.)."""

from __future__ import annotations

import re
from typing import Any

from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch
from app.import_engine.normalize import build_batch_from_sections
from app.import_engine.vin import normalize_vin

_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.I)
_MILEAGE_RE = re.compile(r"(?:mileage|odometer|odo)\s*[:=]?\s*([\d,]+)", re.I)
_CUSTOMER_RE = re.compile(r"(?:customer|name)\s*[:=]\s*(.+)", re.I)
_PHONE_RE = re.compile(r"(?:phone|tel|mobile)\s*[:=]?\s*([+\d\-().\s]{7,})", re.I)
_EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
_YEAR_MAKE_MODEL = re.compile(
    r"\b(19\d{2}|20\d{2})\s+([A-Za-z]+)\s+([A-Za-z0-9\-]+)",
)
_INVOICE_RE = re.compile(r"(?:invoice|inv)\s*[#:]?\s*([A-Za-z0-9\-]+)", re.I)
_AMOUNT_RE = re.compile(r"(?:total|amount|invoice total)\s*[:=]?\s*\$?\s*([\d,]+\.?\d*)", re.I)
_REPAIR_RE = re.compile(r"(?:repair|service|work performed)\s*[:=]\s*(.+)", re.I)
_REC_RE = re.compile(r"(?:recommend(?:ation)?|advisor notes?)\s*[:=]\s*(.+)", re.I)


def extract_from_ocr_text(text: str) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {
        "customers": [],
        "vehicles": [],
        "repairs": [],
        "invoices": [],
        "recommendations": [],
    }

    vin_m = _VIN_RE.search(text)
    vin = normalize_vin(vin_m.group(1)) if vin_m else None
    mileage_m = _MILEAGE_RE.search(text)
    mileage = int(mileage_m.group(1).replace(",", "")) if mileage_m else None
    customer_m = _CUSTOMER_RE.search(text)
    phone_m = _PHONE_RE.search(text)
    email_m = _EMAIL_RE.search(text)
    ymm = _YEAR_MAKE_MODEL.search(text)
    invoice_m = _INVOICE_RE.search(text)
    amount_m = _AMOUNT_RE.search(text)
    repair_m = _REPAIR_RE.search(text)
    rec_m = _REC_RE.search(text)

    customer_name = customer_m.group(1).strip() if customer_m else "Unknown Customer"
    sections["customers"].append(
        {
            "external_id": None,
            "name": customer_name.split("\n")[0][:120],
            "phone": phone_m.group(1).strip() if phone_m else None,
            "email": email_m.group(1) if email_m else None,
            "row_ref": "ocr:customer",
        }
    )

    if vin or ymm:
        sections["vehicles"].append(
            {
                "vin": vin or "",
                "year": int(ymm.group(1)) if ymm else None,
                "make": ymm.group(2) if ymm else None,
                "model": ymm.group(3) if ymm else None,
                "mileage": mileage,
                "customer_name": customer_name.split("\n")[0][:120],
                "row_ref": "ocr:vehicle",
            }
        )

    if repair_m or vin:
        sections["repairs"].append(
            {
                "vin": vin,
                "service_type": "general",
                "description": (repair_m.group(1).strip() if repair_m else "Imported repair"),
                "cost": amount_m.group(1) if amount_m else "0",
                "mileage": mileage,
                "recommendation": rec_m.group(1).strip() if rec_m else None,
                "row_ref": "ocr:repair",
            }
        )

    if invoice_m or amount_m:
        sections["invoices"].append(
            {
                "invoice_number": invoice_m.group(1) if invoice_m else None,
                "vin": vin,
                "amount": amount_m.group(1) if amount_m else "0",
                "status": "paid",
                "row_ref": "ocr:invoice",
            }
        )

    if rec_m:
        sections["recommendations"].append(
            {
                "vin": vin,
                "text": rec_m.group(1).strip(),
                "priority": "normal",
                "row_ref": "ocr:recommendation",
            }
        )

    return {k: v for k, v in sections.items() if v}


class OcrConnector:
    source = ImportSource.OCR

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        text = ""
        if ctx.options.get("ocr_text"):
            text = str(ctx.options["ocr_text"])
        elif ctx.payload:
            # Production path: accept pre-OCR'd text bytes or decode image metadata sidecar.
            # Image OCR engines (Tesseract/cloud) plug in here; default decodes UTF-8 text dumps.
            text = ctx.payload.decode("utf-8", errors="replace")
        else:
            raise ValueError("OCR import requires ocr_text or a text/image payload")

        sections = extract_from_ocr_text(text)
        if not sections:
            batch = NormalizedBatch()
            batch.warnings.append("OCR extracted no recognized fields")
            return batch
        return build_batch_from_sections(sections, source=self.source)
