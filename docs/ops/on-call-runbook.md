# On-call runbook — AI Service Advisor

Primary goals: restore customer-facing availability, communicate status, capture evidence.

## Severity

| Level | Meaning | Response |
|-------|---------|----------|
| SEV-1 | API/web down, data loss risk, auth outage | Page immediately; update `/status` incident |
| SEV-2 | Partial degradation (SMS, AI, billing) | Ack within 15m; incident + workaround |
| SEV-3 | Non-urgent (single shop, cosmetic) | Business hours ticket |

## First 5 minutes

1. Check [Status](http://localhost:3000/status) and `GET /status` (API).
2. Confirm deps: Postgres (`/ready`), Redis, Stripe/Twilio if relevant.
3. Open or update a platform incident (`/platform` → Incidents) with severity + affected components.
4. If deploy-related: note last rollout (`deploy/scripts/rollout.sh` / CI deploy job).
5. Decide: rollback vs forward-fix. Prefer rollback for auth/billing SEV-1.

## Common failures

### API 5xx / not ready

- `GET /live` vs `GET /ready` — ready fails ⇒ DB/Redis.
- Check Alembic: migrations must be at head before traffic.
- Logs: API container / pod; Sentry if `SENTRY_DSN` set.

### Auth / OTP / MFA

- OTP: rows in `auth_otp_challenges`; email provider `fake` vs `smtp`.
- MFA: TOTP clock skew; backup codes path on login.
- Password reset: `/forgot-password` → email link → `/reset-password`.

### Billing / quotas

- Plans: `GET /v1/billing/plans`.
- Stripe unset ⇒ checkout uses **dev activate** path — expected in non-prod.
- Quota 429 on AI/SMS: check shop subscription plan limits.

### SMS / Twilio

- Webhooks idempotent on `twilio_sid`; duplicate SIDs should no-op.
- Outbound failures: credentials + shop SMS quota.

### Enterprise SSO

- Callback: `/enterprise/sso/callback` → `POST /v1/enterprise/sso/callback`.
- Demo mode if no `client_secret`; real OIDC needs IdP redirect URI allow-list.
- `require_sso` blocks password login for linked shops — disable via SSO config if lockout.

## Escalation

1. On-call engineer (primary)
2. Backup on-call
3. Platform owner / engineering lead
4. Vendor (Stripe / Twilio / IdP) if external

Document who is on rotation in your pager tool; keep this file process-oriented only.

## After restore

1. Resolve incident on status page.
2. Short write-up: trigger, impact, fix, follow-ups.
3. If customer data touched: note in compliance evidence folder / access review as needed.
4. Schedule postmortem for SEV-1/2 within 5 business days.

## Related ops scripts

- `deploy/scripts/rollout.sh` — controlled deploy
- `deploy/scripts/backup-drill.sh` — restore evidence
- `scripts/saas_smoke.py` — post-deploy smoke checks
