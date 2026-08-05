"""Voice plugin interfaces."""

from __future__ import annotations

from typing import Any, Protocol

from app.plugins.framework.context import PluginContext
from app.plugins.voice.metrics import VoiceMetricsCollector
from app.plugins.voice.session.service import VoiceSessionService


class IVoicePlugin(Protocol):
    def plugin_id(self) -> str: ...

    def supported_capabilities(self) -> list[str]: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...

    @property
    def sessions(self) -> VoiceSessionService: ...

    @property
    def metrics(self) -> VoiceMetricsCollector: ...

    async def health_check(self) -> dict[str, Any]: ...
