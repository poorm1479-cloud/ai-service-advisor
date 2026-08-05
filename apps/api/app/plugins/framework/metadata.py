"""Plugin metadata + validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+([.-][A-Za-z0-9.-]+)?$")


@dataclass(slots=True)
class PluginMetadata:
    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
            "aliases": dict(self.aliases),
            **dict(self.extra),
        }


def validate_metadata(meta: PluginMetadata) -> list[str]:
    """Return validation errors (empty = valid)."""
    errors: list[str] = []
    if not meta.plugin_id or not str(meta.plugin_id).strip():
        errors.append("plugin_id is required")
    if not meta.name or not str(meta.name).strip():
        errors.append("name is required")
    if not meta.version or not _SEMVER.match(str(meta.version)):
        errors.append("version must be semver (e.g. 1.0.0)")
    if not meta.capabilities:
        errors.append("at least one capability is required")
    seen: set[str] = set()
    for cap in meta.capabilities:
        if not cap:
            errors.append("empty capability name")
        elif cap in seen:
            errors.append(f"duplicate capability in metadata: {cap}")
        seen.add(cap)
    return errors
