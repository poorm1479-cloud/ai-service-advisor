# ADR 0002 — Phase 1 Clean Architecture foundation

## Status

Accepted

## Context

Phase 0 used a pragmatic modular layout. Phase 1 needs clearer boundaries for auth,
tenancy, and future domain growth (vehicles, ROs, agents).

## Decision

Reorganize `apps/api` into Clean Architecture layers:

- `domain` — entities, enums, repository ports, exceptions
- `application` — auth / customer use cases
- `infrastructure` — SQLAlchemy, security, UoW adapters
- `api` — FastAPI routers, schemas, dependencies

Rename tenant model to **Shop**. Persist refresh tokens (hashed). Roles:
Owner, Manager, Service Advisor, Mechanic.

## Consequences

- Application services are testable without HTTP.
- Shop isolation remains enforced via `shop_id` + RLS (`app.shop_id` GUC).
- Frontend consumes `/v1/auth/*` with access + refresh tokens.
