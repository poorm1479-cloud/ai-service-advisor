"""Shopmonkey API connector."""

from __future__ import annotations

from app.import_engine.connectors.api_common import fetch_or_sample
from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch


class ShopmonkeyConnector:
    source = ImportSource.SHOPMONKEY

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        return await fetch_or_sample(
            provider="shopmonkey",
            source=self.source,
            base_url=ctx.credentials.get("base_url") or "https://api.shopmonkey.cloud/v3",
            api_key=ctx.credentials.get("api_key"),
            path=ctx.options.get("path", "/export"),
            use_sample=bool(ctx.options.get("use_sample", True)),
        )
