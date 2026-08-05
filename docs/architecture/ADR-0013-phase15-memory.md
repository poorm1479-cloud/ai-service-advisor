# ADR 0013 — Phase 15 Long-Term AI Memory

## Status

Accepted (Phase 15)

## Context

Short-term SMS/voice session memory is not enough. Agents need durable recall of
customer preferences, communication style, vehicle history, prior conversations,
repair decisions, declined estimates, and appointment behavior — across sessions.

## Decision

1. Add `apps/api/app/memory/` with:
   - **Memory types** — Semantic, Conversation, Customer, Business
   - **Categories** — preferences, style, vehicle history, conversations,
     repair decisions, declined estimates, appointment behavior
   - **Indexer** — write/dedupe with local hashing embeddings
   - **Retriever** — hybrid semantic + lexical + importance scoring
   - **MemoryAutoPilot** — auto-load before pipeline, auto-capture after stages
2. Wire into `AgentOrchestrator` so memory is injected into
   `AgentContext.metadata` (`long_term_memory`, `memory_prompt`,
   `communication_style`) without callers opting in.
3. SMS/Voice reply generators consume communication style automatically.
4. HTTP API `/v1/memory/*`, UI `/dashboard/memory`, Alembic `0015_phase15_memory`.

```mermaid
flowchart LR
  Inbound --> Orch[Orchestrator]
  Orch -->|auto_load| Mem[Long-Term Memory]
  Mem --> Ctx[AgentContext.metadata]
  Ctx --> Agents
  Agents --> Orch
  Orch -->|auto_capture| Mem
```

## Consequences

- Pipeline never blocks on memory failures (soft-fail + log).
- Embeddings are local hashing-trick vectors — swapable for OpenAI embeddings later.
- Short-term sms/voice memory remains the turn buffer; long-term memory is durable.
