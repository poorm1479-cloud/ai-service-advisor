# ADR 0018 — Architecture Refactor Phase 7: Unified Conversation Domain

Status: Accepted (Architecture Refactor Phase 7)

## Context

Customer interactions were split across SMS conversations, Voice calls, CRM timeline
entries, and agent channel labels. Workflow needed a single ConversationId, with
channels as adapters only.

## Decision

Introduce `plugins/conversation` implementing `IPlugin` + `IConversationPlugin`.

- Conversation aggregate owns messages, timeline, AI insights, workflow history, channel history
- Phone, SMS, Email, Facebook, Website Chat, Walk-in (+ future WhatsApp/Instagram/GBM) are adapters
- Existing SMS/Voice modules remain; adapters wrap them without rewrite
- Orchestrator creates/updates a Conversation on every inbound message
- Workflow DecisionExecutor records summaries/escalations/decisions on ConversationId
- No database schema change — in-memory unified store facades transport IDs (SMS/Voice UUIDs)

## Capabilities

CreateConversation, FindConversation, UpdateConversation, CloseConversation,
MergeConversation, SearchConversation, ConversationHistory, ConversationSummary

## Consequences

- Workflow operates on ConversationId (not channel transport IDs)
- CRM communication timeline capabilities remain on CRM Plugin
- Public `/v1` SMS/Voice/agent APIs unchanged
