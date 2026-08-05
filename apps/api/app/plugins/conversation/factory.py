"""Conversation Plugin factory."""

from __future__ import annotations

from typing import Any

from app.plugins.conversation.plugin import ConversationPlugin
from app.plugins.framework.metadata import PluginMetadata

_plugin: ConversationPlugin | None = None


def build_conversation_plugin(
    *,
    store: Any | None = None,
    adapters: dict[str, Any] | None = None,
    register: bool = True,
) -> ConversationPlugin:
    kwargs: dict[str, Any] = {}
    if store is not None:
        kwargs["store"] = store
    if adapters is not None:
        kwargs["adapters"] = adapters
    plugin = ConversationPlugin(**kwargs)
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "conversation.create": "CreateConversation",
                "conversation.find": "FindConversation",
                "conversation.update": "UpdateConversation",
                "conversation.close": "CloseConversation",
                "conversation.summary": "ConversationSummary",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_conversation_plugin() -> ConversationPlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("conversation")  # type: ignore[assignment]
    return _plugin


def reset_conversation_plugin() -> None:
    global _plugin
    _plugin = None


def conversation_plugin_from_ports(
    *,
    store: Any | None = None,
    adapters: dict[str, Any] | None = None,
) -> ConversationPlugin:
    return build_conversation_plugin(store=store, adapters=adapters, register=False)
