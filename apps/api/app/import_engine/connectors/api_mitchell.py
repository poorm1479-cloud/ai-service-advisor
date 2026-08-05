"""Mitchell API connector."""

from __future__ import annotations

from app.import_engine.connectors.api_common import fetch_or_sample
from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch


class MitchellConnector:
    source = ImportSource.MITCHELL

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        return await fetch_or_sample(
            provider="mitchell",
            source=self.source,
            base_url=ctx.credentials.get("base_url") or "https://api.mitchell.com/v1",
            api_key=ctx.credentials.get("api_key"),
            path=ctx.options.get("path", "/export"),
            use_sample=bool(ctx.options.get("use_sample", True)),
        )
