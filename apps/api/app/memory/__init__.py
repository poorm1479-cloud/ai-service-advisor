"""Phase 15 — Long-Term AI Memory.

Durable cross-session memory that AI agents load and update automatically.
"""

from app.memory.factory import (
    MemoryRuntime,
    build_memory_runtime,
    get_memory_runtime,
    reset_memory_runtime,
)

__all__ = [
    "MemoryRuntime",
    "build_memory_runtime",
    "get_memory_runtime",
    "reset_memory_runtime",
]
