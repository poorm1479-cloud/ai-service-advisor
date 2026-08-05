"""MCP tool descriptor and registry (Protocol-compatible surface)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.base.errors import AgentValidationError


@dataclass(slots=True)
class McpTool:
    """Minimal MCP tool descriptor — maps cleanly to MCP ``tools/list`` + ``tools/call``."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    agent: str
    tags: list[str] = field(default_factory=list)

    def to_mcp_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"agent": self.agent, "tags": self.tags},
        }


class McpToolRegistry:
    """Registry of agent-backed tools for future MCP server wiring."""

    def __init__(self) -> None:
        self._tools: dict[str, McpTool] = {}

    def register(self, tool: McpTool) -> None:
        if tool.name in self._tools:
            raise AgentValidationError(f"MCP tool already registered: {tool.name}", agent="mcp")
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_mcp_descriptor() for t in self._tools.values()]

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise AgentValidationError(f"Unknown MCP tool: {name}", agent="mcp")
        return await tool.handler(arguments or {})

    @classmethod
    def from_runtime(cls, **agents: Any) -> McpToolRegistry:
        from app.agents.mcp.tools import build_default_mcp_tools

        registry = cls()
        for tool in build_default_mcp_tools(**agents):
            registry.register(tool)
        return registry
