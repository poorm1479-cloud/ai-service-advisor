"""MCP Hub monitoring counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class McpHubMonitor:
    connections_created: int = 0
    connections_connected: int = 0
    connections_disconnected: int = 0
    invokes: int = 0
    invoke_failures: int = 0
    retries: int = 0
    permission_denials: int = 0
    tests: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)

    def record_created(self, provider: str) -> None:
        self.connections_created += 1
        self.by_provider[provider] = self.by_provider.get(provider, 0) + 1

    def record_connected(self) -> None:
        self.connections_connected += 1

    def record_disconnected(self) -> None:
        self.connections_disconnected += 1

    def record_invoke(self, provider: str, *, ok: bool) -> None:
        self.invokes += 1
        self.by_provider[provider] = self.by_provider.get(provider, 0) + 1
        if not ok:
            self.invoke_failures += 1

    def record_retry(self) -> None:
        self.retries += 1

    def record_denied(self) -> None:
        self.permission_denials += 1

    def record_test(self) -> None:
        self.tests += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "connections_created": self.connections_created,
            "connections_connected": self.connections_connected,
            "connections_disconnected": self.connections_disconnected,
            "invokes": self.invokes,
            "invoke_failures": self.invoke_failures,
            "retries": self.retries,
            "permission_denials": self.permission_denials,
            "tests": self.tests,
            "by_provider": dict(self.by_provider),
        }
