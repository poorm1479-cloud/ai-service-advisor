"""Production Voice AI Integration — communication adapter plugin."""

from app.plugins.voice.factory import (
    build_voice_plugin,
    get_voice_plugin,
    reset_voice_plugin,
)
from app.plugins.voice.plugin import VoicePlugin

__all__ = [
    "VoicePlugin",
    "build_voice_plugin",
    "get_voice_plugin",
    "reset_voice_plugin",
]
