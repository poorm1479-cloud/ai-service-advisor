# ADR 0020 — Architecture Refactor Phase 9: AI Service Advisor

Status: Accepted (Architecture Refactor Phase 9)

## Context

The platform needed a digital Service Advisor spanning reception → estimate →
repair updates → follow-up → retention. This must not be a chatbot that mutates
systems. AI proposes Decision Objects; Workflow executes via business plugins.

## Decision

Add `plugins/advisor` (AI Service Advisor) as a decide-only plugin:

- Capabilities: AnalyzeConversation, AnalyzeCustomer, AnalyzeVehicle,
  GenerateRepairRecommendation, GenerateEstimateSummary, GenerateCustomerExplanation,
  GenerateApprovalRequest, GenerateRepairUpdate, GenerateFollowUp,
  GenerateMaintenanceReminder, GenerateReviewRequest, GenerateRetentionPlan
- New Decision types for repair/estimate/approval/status/maintenance/review/retention/communication
- Orchestrator runs Advisor after Conversation + domain analysis; Workflow DecisionExecutor applies

## AI must never

Book appointments, modify CRM/DB, send messages, dispatch marketing, or process payments.

## Consequences

- Flow: Workflow → Conversation → Advisor → Decisions → DecisionExecutor → Plugins
- Existing SMS/Voice/CRM/Scheduling/Revenue public APIs unchanged
- No database schema change
