"""Plugin lifecycle states and transitions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.plugins.framework.context import PluginContext
from app.plugins.framework.plugin import IPlugin


class LifecycleState(StrEnum):
    INSTALLED = "installed"
    INITIALIZED = "initialized"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UPGRADING = "upgrading"
    ROLLING_BACK = "rolling_back"
    UNINSTALLED = "uninstalled"


# Allowed transitions: from → to
_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.INSTALLED: {LifecycleState.INITIALIZED, LifecycleState.UNINSTALLED},
    LifecycleState.INITIALIZED: {
        LifecycleState.ENABLED,
        LifecycleState.DISABLED,
        LifecycleState.UNINSTALLED,
    },
    LifecycleState.ENABLED: {
        LifecycleState.DISABLED,
        LifecycleState.UPGRADING,
        LifecycleState.UNINSTALLED,
    },
    LifecycleState.DISABLED: {
        LifecycleState.ENABLED,
        LifecycleState.UNINSTALLED,
        LifecycleState.UPGRADING,
    },
    LifecycleState.UPGRADING: {LifecycleState.ENABLED, LifecycleState.ROLLING_BACK},
    LifecycleState.ROLLING_BACK: {LifecycleState.ENABLED, LifecycleState.DISABLED},
    LifecycleState.UNINSTALLED: set(),
}


class PluginLifecycle:
    """Manages lifecycle transitions for a registered plugin."""

    def __init__(self, plugin: IPlugin, *, state: LifecycleState = LifecycleState.INSTALLED) -> None:
        self.plugin = plugin
        self.state = state
        self._version_history: list[str] = [plugin.plugin_version()]

    def can_transition(self, target: LifecycleState) -> bool:
        return target in _TRANSITIONS.get(self.state, set())

    def _transition(self, target: LifecycleState) -> None:
        if not self.can_transition(target):
            raise ValueError(f"Cannot transition {self.state.value} → {target.value}")
        self.state = target

    async def install(self) -> None:
        """Mark as installed (already constructed)."""
        if self.state == LifecycleState.UNINSTALLED:
            self.state = LifecycleState.INSTALLED
        elif self.state != LifecycleState.INSTALLED:
            # Idempotent install from installed
            if self.state == LifecycleState.INSTALLED:
                return
            raise ValueError(f"Cannot install from state {self.state.value}")

    async def initialize(self, context: PluginContext | None = None) -> None:
        if self.state == LifecycleState.INSTALLED:
            await self.plugin.initialize(context)
            self._transition(LifecycleState.INITIALIZED)
        elif self.state in {LifecycleState.INITIALIZED, LifecycleState.ENABLED, LifecycleState.DISABLED}:
            return
        else:
            raise ValueError(f"Cannot initialize from state {self.state.value}")

    async def enable(self) -> None:
        if self.state == LifecycleState.INITIALIZED:
            self._transition(LifecycleState.ENABLED)
        elif self.state == LifecycleState.DISABLED:
            self._transition(LifecycleState.ENABLED)
        elif self.state == LifecycleState.ENABLED:
            return
        else:
            raise ValueError(f"Cannot enable from state {self.state.value}")

    async def disable(self) -> None:
        if self.state == LifecycleState.ENABLED:
            self._transition(LifecycleState.DISABLED)
        elif self.state in {LifecycleState.DISABLED, LifecycleState.INITIALIZED}:
            self.state = LifecycleState.DISABLED
        else:
            raise ValueError(f"Cannot disable from state {self.state.value}")

    async def upgrade(self, new_version: str) -> None:
        if self.state not in {LifecycleState.ENABLED, LifecycleState.DISABLED}:
            raise ValueError(f"Cannot upgrade from state {self.state.value}")
        prev = self.state
        self.state = LifecycleState.UPGRADING
        self._version_history.append(new_version)
        self.state = LifecycleState.ENABLED if prev == LifecycleState.ENABLED else LifecycleState.DISABLED

    async def rollback(self) -> str:
        if len(self._version_history) < 2:
            raise ValueError("No previous version to rollback to")
        self.state = LifecycleState.ROLLING_BACK
        self._version_history.pop()
        restored = self._version_history[-1]
        self.state = LifecycleState.ENABLED
        return restored

    async def uninstall(self) -> None:
        if self.state == LifecycleState.UNINSTALLED:
            return
        if self.state == LifecycleState.ENABLED:
            await self.disable()
        await self.plugin.shutdown()
        self.state = LifecycleState.UNINSTALLED

    def snapshot(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin.plugin_id(),
            "state": self.state.value,
            "version": self.plugin.plugin_version(),
            "version_history": list(self._version_history),
        }
