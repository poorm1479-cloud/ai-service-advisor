"""PDF connector — extract text then reuse OCR field parsers."""

from __future__ import annotations

import io

from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.connectors.ocr_connector import extract_from_ocr_text
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch
from app.import_engine.normalize import build_batch_from_sections


def extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF import") from exc

    reader = PdfReader(io.BytesIO(payload))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


class PdfConnector:
    source = ImportSource.PDF

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        if not ctx.payload:
            raise ValueError("PDF import requires an uploaded file")
        text = extract_pdf_text(ctx.payload)
        if not text.strip():
            batch = NormalizedBatch()
            batch.warnings.append("PDF contained no extractable text; try OCR import")
            return batch
        sections = extract_from_ocr_text(text)
        if not sections:
            batch = NormalizedBatch()
            batch.warnings.append("PDF text parsed but no shop fields detected")
            return batch
        return build_batch_from_sections(sections, source=self.source)
