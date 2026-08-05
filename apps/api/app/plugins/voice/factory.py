"""Production Voice AI plugin factory."""

from __future__ import annotations

from typing import Any

from app.plugins.framework.metadata import PluginMetadata
from app.plugins.voice.plugin import VoicePlugin

_plugin: VoicePlugin | None = None


def build_voice_plugin(*, register: bool = True) -> VoicePlugin:
    plugin = VoicePlugin()
    if register:
        from app.plugins.framework.factory import get_plugin_runtime

        meta = PluginMetadata(
            plugin_id=plugin.plugin_id(),
            name=plugin.plugin_name(),
            version=plugin.plugin_version(),
            description=plugin.plugin_description(),
            capabilities=list(plugin.supported_capabilities()),
            aliases={
                "voice.receive": "ReceiveCall",
                "voice.session": "CreateVoiceSession",
                "voice.stt": "SpeechToText",
                "voice.tts": "TextToSpeech",
                "voice.transfer": "TransferToHuman",
                "voice.end": "EndCall",
                "voice.record": "RecordConversation",
            },
        )
        get_plugin_runtime().plugins.register(
            plugin, metadata=meta, replace_capabilities=True
        )
        plugin._initialized = True
    return plugin


def get_voice_plugin() -> VoicePlugin:
    global _plugin
    if _plugin is None:
        from app.plugins.framework.factory import ensure_default_plugins
        from app.plugins.framework.registry import get_plugin_registry

        ensure_default_plugins()
        _plugin = get_plugin_registry().lookup("voice")  # type: ignore[assignment]
    return _plugin


def reset_voice_plugin() -> None:
    global _plugin
    _plugin = None


def voice_plugin_from_ports(**_kwargs: Any) -> VoicePlugin:
    return build_voice_plugin(register=False)
