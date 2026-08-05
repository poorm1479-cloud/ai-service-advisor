"""Connector protocol and registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch


@dataclass(slots=True)
class ConnectorContext:
    shop_id: UUID
    source: ImportSource
    credentials: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    payload: bytes | None = None
    filename: str | None = None
    content_type: str | None = None
    manual_sections: dict[str, list[dict[str, Any]]] | None = None


class ImportConnector(Protocol):
    source: ImportSource

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch: ...


def get_connector(source: ImportSource) -> ImportConnector:
    from app.import_engine.connectors.api_autoleap import AutoLeapConnector
    from app.import_engine.connectors.api_mitchell import MitchellConnector
    from app.import_engine.connectors.api_shopmonkey import ShopmonkeyConnector
    from app.import_engine.connectors.api_tekmetric import TekmetricConnector
    from app.import_engine.connectors.csv_connector import CsvConnector
    from app.import_engine.connectors.excel_connector import ExcelConnector
    from app.import_engine.connectors.manual_connector import ManualConnector
    from app.import_engine.connectors.ocr_connector import OcrConnector
    from app.import_engine.connectors.pdf_connector import PdfConnector

    registry: dict[ImportSource, ImportConnector] = {
        ImportSource.TEKMETRIC: TekmetricConnector(),
        ImportSource.SHOPMONKEY: ShopmonkeyConnector(),
        ImportSource.AUTOLEAP: AutoLeapConnector(),
        ImportSource.MITCHELL: MitchellConnector(),
        ImportSource.CSV: CsvConnector(),
        ImportSource.EXCEL: ExcelConnector(),
        ImportSource.PDF: PdfConnector(),
        ImportSource.OCR: OcrConnector(),
        ImportSource.MANUAL: ManualConnector(),
    }
    return registry[source]
