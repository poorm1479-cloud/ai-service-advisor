"""IPlugin — common plugin contract for AutoRepair OS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from app.plugins.framework.context import PluginContext


@runtime_checkable
class IPlugin(Protocol):
    """Common interface every AutoRepair OS plugin must satisfy."""

    def plugin_id(self) -> str: ...

    def plugin_name(self) -> str: ...

    def plugin_version(self) -> str: ...

    def plugin_description(self) -> str: ...

    def supported_capabilities(self) -> list[str]: ...

    async def initialize(self, context: PluginContext | None = None) -> None: ...

    async def shutdown(self) -> None: ...

    async def health_check(self) -> dict[str, Any]: ...

    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...


class BasePlugin(ABC):
    """Optional base class with default lifecycle/health implementations."""

    _initialized: bool = False

    @abstractmethod
    def plugin_id(self) -> str: ...

    @abstractmethod
    def plugin_name(self) -> str: ...

    def plugin_version(self) -> str:
        return "1.0.0"

    def plugin_description(self) -> str:
        return ""

    @abstractmethod
    def supported_capabilities(self) -> list[str]: ...

    async def initialize(self, context: PluginContext | None = None) -> None:
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id(),
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.plugin_version(),
        }

    @abstractmethod
    async def invoke(
        self,
        capability: str,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any: ...
