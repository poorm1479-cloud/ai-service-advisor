# Change advisory (CAB) — template

Use for production deploys that touch auth, billing, data retention, or multi-tenant isolation.

## Change ID

- **Title:**
- **Date / window (UTC):**
- **Author / approver:**
- **Risk:** Low / Medium / High
- **Rollback plan:** yes / no (describe)

## Summary

What is changing and why (1–3 sentences).

## Scope

- Services: API / Web / DB migrations / Infra
- Migrations: none / Alembic revision(s) ______
- Feature flags / env vars:

## Pre-checks

- [ ] CI green on the release commit
- [ ] `scripts/saas_smoke.py` against staging
- [ ] Backup taken or PITR confirmed (if schema/data change)
- [ ] Status page ready for SEV communication
- [ ] On-call aware of window

## Execution

1.
2.
3.

## Validation

- [ ] `/health` and `/ready` OK
- [ ] Login + MFA path
- [ ] Billing plans list
- [ ] Status page loads
- [ ] Critical shop smoke (optional)

## Rollback

Steps and decision criteria (who decides).

## Evidence

Link PR, deploy job, backup-drill output, or incident ID if any.
