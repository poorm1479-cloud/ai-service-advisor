"""Manual JSON entry connector."""

from __future__ import annotations

from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch
from app.import_engine.normalize import build_batch_from_sections


class ManualConnector:
    source = ImportSource.MANUAL

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        sections = ctx.manual_sections or ctx.options.get("sections")
        if not sections or not isinstance(sections, dict):
            raise ValueError("Manual import requires sections payload")
        return build_batch_from_sections(sections, source=self.source)
