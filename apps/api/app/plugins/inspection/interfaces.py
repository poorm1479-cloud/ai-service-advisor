"""Inspection Intelligence interfaces."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.plugins.framework.context import PluginContext
from app.plugins.inspection.models import InspectionContext, InspectionPlan, InspectionRecord
from app.plugins.inspection.store import InspectionStore


class IInspectionPlugin(Protocol):
    def plugin_id(self) -> str: ...

    def supported_capabilities(self) -> list[str]: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def build_context(self, **kwargs: Any) -> InspectionContext: ...

    def analyze(self, ctx: InspectionContext) -> InspectionPlan: ...

    @property
    def store(self) -> InspectionStore: ...

    async def health_check(self) -> dict[str, Any]: ...


class IInspectionStore(Protocol):
    def save(self, record: InspectionRecord) -> InspectionRecord: ...

    def get(self, inspection_id: UUID) -> InspectionRecord | None: ...

    def list_for_shop(self, shop_id: UUID, *, limit: int = 50) -> list[InspectionRecord]: ...
