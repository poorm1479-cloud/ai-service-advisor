"""AI Service Advisor ports — decide-only plugin contract."""

from __future__ import annotations

from typing import Any, Protocol

from app.plugins.advisor.models import AdvisorContext, AdvisorPlan
from app.plugins.framework.context import PluginContext


class IAdvisorPlugin(Protocol):
    def plugin_id(self) -> str: ...

    def advise(self, ctx: AdvisorContext) -> AdvisorPlan: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...
