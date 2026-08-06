"""Shared Voice runtime singleton."""

from __future__ import annotations

from app.voice.factory import VoiceRuntime, build_voice_runtime

_runtime: VoiceRuntime | None = None


def get_voice_runtime() -> VoiceRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_voice_runtime()
    return _runtime


def peek_voice_runtime() -> VoiceRuntime | None:
    """Return the singleton if already built — never cold-starts the AI stack."""
    return _runtime


def reset_voice_runtime() -> None:
    global _runtime
    _runtime = None
