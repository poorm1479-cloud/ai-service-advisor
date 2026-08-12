"""Process-local OpenAI kill switch (synced from platform_settings)."""

from __future__ import annotations

_openai_enabled: bool = True


def is_openai_enabled() -> bool:
    return _openai_enabled


def set_openai_enabled(value: bool) -> None:
    global _openai_enabled
    _openai_enabled = bool(value)
