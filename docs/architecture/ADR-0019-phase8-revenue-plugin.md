# ADR 0019 — Architecture Refactor Phase 8: Revenue Intelligence Engine Plugin

Status: Accepted (Architecture Refactor Phase 8)

## Context

Revenue logic already existed in `app/revenue_intel` (Phase 11) and `app/agents/revenue`
(Phase 5). Workflow was calling `get_revenue_intel_runtime` directly for live sources and
treated `RevenueDecision` as decide-only. Phase 8 makes Revenue a Plugin so Workflow only
uses the Capability Registry.

## Decision

Add `plugins/revenue` implementing `IPlugin` + `IRevenuePlugin`, wrapping (not rewriting)
`RevenueIntelService`, scoring, messaging, and optionally Scheduling utilization snapshots.

Purpose is opportunity prioritization — not accounting reports.

## Capabilities

DetectRevenueOpportunity, PredictMaintenance, PredictCustomerReturn, FindDeclinedEstimates,
GenerateUpsellRecommendations, GenerateCrossSellRecommendations, CalculateVehicleHealth,
CalculateCustomerHealth, CalculateCustomerLifetimeValue, PredictShopCapacity,
OptimizeTechnicianUtilization

## Consequences

- Workflow → Capability Registry → Revenue Plugin → revenue_intel
- Detected opportunities emit workflow events (follow-up, reminder, escalate high-value)
- `/v1/revenue` and frontend revenue dashboard remain unchanged
- No database schema change
