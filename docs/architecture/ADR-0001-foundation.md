# ADR 0001 — Modular monolith + shared-schema tenancy

## Status

Accepted (Phase 0)

## Context

Independent auto repair shops need a multi-tenant SaaS with strict data isolation,
without the ops cost of microservices or database-per-tenant.

## Decision

1. Ship a **modular FastAPI monolith** (`apps/api`) with domain packages.
2. Use **shared PostgreSQL schema** with mandatory `tenant_id` and **RLS** on tenant business tables.
3. Keep **Next.js** as a separate app talking over versioned HTTP (`/v1`).
4. Defer Redis-backed jobs until communications/AI phases; compose still provisions Redis.

## Consequences

- Faster Phase 0 delivery and simpler local DX.
- Must maintain defense in depth (app filters + RLS + cache key prefixes later).
- Schema-per-tenant or service splits remain open if franchise/scale needs appear.
