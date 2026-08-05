"""CSV file connector."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

from app.import_engine.connectors.base import ConnectorContext
from app.import_engine.enums import ImportSource
from app.import_engine.models import NormalizedBatch
from app.import_engine.normalize import build_batch_from_sections

ENTITY_ALIASES = {
    "customer": "customers",
    "customers": "customers",
    "vehicle": "vehicles",
    "vehicles": "vehicles",
    "repair": "repairs",
    "repairs": "repairs",
    "repair_history": "repairs",
    "invoice": "invoices",
    "invoices": "invoices",
    "estimate": "estimates",
    "estimates": "estimates",
    "communication": "communications",
    "communications": "communications",
    "appointment": "appointments",
    "appointments": "appointments",
    "recommendation": "recommendations",
    "recommendations": "recommendations",
}


class CsvConnector:
    source = ImportSource.CSV

    async def extract(self, ctx: ConnectorContext) -> NormalizedBatch:
        if not ctx.payload:
            raise ValueError("CSV import requires an uploaded file")
        if ctx.payload.startswith(b"PK"):
            raise ValueError(
                "File looks like Excel (.xlsx). Re-run import with Excel selected, or rename to .xlsx."
            )
        text = ctx.payload.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
        entity_col = None
        for name in reader.fieldnames:
            if name and name.lower() in ("entity", "entity_type", "type", "record_type"):
                entity_col = name
                break

        default_entity = str(ctx.options.get("entity") or "customers").lower()
        default_entity = ENTITY_ALIASES.get(default_entity, default_entity)

        for i, row in enumerate(reader, start=2):
            cleaned = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
            if entity_col and cleaned.get(entity_col):
                ent = ENTITY_ALIASES.get(str(cleaned.pop(entity_col)).lower().strip(), "customers")
            else:
                ent = default_entity
            cleaned["row_ref"] = f"csv:{i}"
            sections[ent].append(cleaned)

        if not sections:
            raise ValueError("CSV contained no data rows")
        return build_batch_from_sections(dict(sections), source=self.source)
