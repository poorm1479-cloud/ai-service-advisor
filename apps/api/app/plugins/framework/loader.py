"""Plugin loader — discover and load plugin modules/factories."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.framework.plugin import IPlugin
from app.plugins.framework.registry import PluginRegistry, get_plugin_registry

logger = logging.getLogger("asa.plugins.loader")

PluginFactory = Callable[..., IPlugin]


class PluginLoader:
    """Load plugins from callables or import paths and install into the registry."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self._registry = registry or get_plugin_registry()

    def load_factory(
        self,
        factory: PluginFactory,
        *,
        metadata: PluginMetadata | None = None,
        **factory_kwargs: Any,
    ) -> IPlugin:
        plugin = factory(**factory_kwargs)
        self._registry.register(plugin, metadata=metadata, replace_capabilities=True)
        return plugin

    async def load_and_install(
        self,
        factory: PluginFactory,
        *,
        metadata: PluginMetadata | None = None,
        enable: bool = True,
        **factory_kwargs: Any,
    ) -> IPlugin:
        plugin = factory(**factory_kwargs)
        await self._registry.install(plugin, metadata=metadata, enable=enable)
        return plugin

    def load_module(
        self,
        module_path: str,
        *,
        attr: str = "build_plugin",
        metadata: PluginMetadata | None = None,
        **kwargs: Any,
    ) -> IPlugin:
        module = importlib.import_module(module_path)
        factory = getattr(module, attr, None)
        if factory is None:
            raise ImportError(f"{module_path} has no attribute {attr}")
        logger.info("plugin.loader module=%s attr=%s", module_path, attr)
        return self.load_factory(factory, metadata=metadata, **kwargs)

    def load_crm_reference(self, **kwargs: Any) -> IPlugin:
        """Convenience: load the CRM reference plugin via its factory."""
        from app.plugins.crm.factory import build_crm_plugin

        return self.load_factory(lambda **kw: build_crm_plugin(register=False, **kw), **kwargs)
