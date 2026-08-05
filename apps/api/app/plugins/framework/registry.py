"""Plugin Registry — install, lookup, versioned plugins, metadata validation."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.capability import get_capability_registry
from app.plugins.framework.context import PluginContext
from app.plugins.framework.lifecycle import LifecycleState, PluginLifecycle
from app.plugins.framework.metadata import PluginMetadata, validate_metadata
from app.plugins.framework.plugin import IPlugin


class PluginRegistry:
    """Central registry of installed plugins."""

    def __init__(self) -> None:
        # plugin_id → version → lifecycle
        self._by_id: dict[str, dict[str, PluginLifecycle]] = {}
        self._metadata: dict[str, PluginMetadata] = {}  # plugin_id@version

    def _key(self, plugin_id: str, version: str) -> str:
        return f"{plugin_id}@{version}"

    def register(
        self,
        plugin: IPlugin,
        *,
        metadata: PluginMetadata | None = None,
        enable: bool = True,
        replace_capabilities: bool = True,
    ) -> PluginLifecycle:
        """Install + initialize (+ enable) a plugin and bind capabilities."""
        meta = metadata or PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
        )
        errors = validate_metadata(meta)
        if errors:
            raise ValueError(f"Invalid plugin metadata: {'; '.join(errors)}")

        plugin_id = meta.plugin_id
        version = meta.version
        versions = self._by_id.setdefault(plugin_id, {})
        if version in versions and versions[version].state != LifecycleState.UNINSTALLED:
            # Re-bind capabilities for same version (idempotent)
            life = versions[version]
        else:
            life = PluginLifecycle(plugin, state=LifecycleState.INSTALLED)
            versions[version] = life

        self._metadata[self._key(plugin_id, version)] = meta

        # Bind capabilities via Capability Registry
        get_capability_registry().register_plugin(
            plugin, replace=replace_capabilities, aliases=meta.aliases or None
        )
        return life

    async def install(
        self,
        plugin: IPlugin,
        *,
        metadata: PluginMetadata | None = None,
        context: PluginContext | None = None,
        enable: bool = True,
    ) -> PluginLifecycle:
        life = self.register(plugin, metadata=metadata, replace_capabilities=True)
        await life.initialize(context)
        if enable:
            await life.enable()
        return life

    def lookup(self, plugin_id: str, version: str | None = None) -> IPlugin:
        versions = self._by_id.get(plugin_id)
        if not versions:
            raise LookupError(f"Plugin not found: {plugin_id}")
        if version:
            life = versions.get(version)
            if life is None or life.state == LifecycleState.UNINSTALLED:
                raise LookupError(f"Plugin version not found: {plugin_id}@{version}")
            return life.plugin
        # Prefer enabled, then highest semver-ish string
        enabled = [
            life
            for life in versions.values()
            if life.state == LifecycleState.ENABLED
        ]
        if enabled:
            enabled.sort(key=lambda l: l.plugin.plugin_version(), reverse=True)
            return enabled[0].plugin
        active = [
            life
            for life in versions.values()
            if life.state != LifecycleState.UNINSTALLED
        ]
        if not active:
            raise LookupError(f"Plugin not found: {plugin_id}")
        active.sort(key=lambda l: l.plugin.plugin_version(), reverse=True)
        return active[0].plugin

    def resolve_by_capability(self, capability: str) -> IPlugin:
        return get_capability_registry().resolve_plugin(capability)

    def get_lifecycle(self, plugin_id: str, version: str | None = None) -> PluginLifecycle:
        plugin = self.lookup(plugin_id, version)
        versions = self._by_id[plugin_id]
        for life in versions.values():
            if life.plugin is plugin:
                return life
        raise LookupError(f"Lifecycle not found: {plugin_id}")

    def list_plugins(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for plugin_id, versions in sorted(self._by_id.items()):
            for version, life in sorted(versions.items()):
                if life.state == LifecycleState.UNINSTALLED:
                    continue
                meta = self._metadata.get(self._key(plugin_id, version))
                rows.append(
                    {
                        **life.snapshot(),
                        "name": meta.name if meta else life.plugin.plugin_name(),
                        "description": meta.description
                        if meta
                        else life.plugin.plugin_description(),
                        "capabilities": list(
                            meta.capabilities
                            if meta
                            else life.plugin.supported_capabilities()
                        ),
                    }
                )
        return rows

    async def enable(self, plugin_id: str, version: str | None = None) -> None:
        await self.get_lifecycle(plugin_id, version).enable()

    async def disable(self, plugin_id: str, version: str | None = None) -> None:
        await self.get_lifecycle(plugin_id, version).disable()

    async def uninstall(self, plugin_id: str, version: str | None = None) -> None:
        life = self.get_lifecycle(plugin_id, version)
        await life.uninstall()
        get_capability_registry().unbind_plugin(plugin_id)

    def clear(self) -> None:
        self._by_id.clear()
        self._metadata.clear()


_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_plugin_registry() -> None:
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
