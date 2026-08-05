# SOC 2 readiness controls (starter checklist)

This is an engineering checklist for preparing AI Service Advisor for a SOC 2 Type I/II engagement.
It is not legal advice and does not replace a formal audit.

## Access control
- [x] Shop multi-tenancy with RLS (`shop_id`)
- [x] Role/capability permissions (owner/staff/ai_agent)
- [x] MFA (TOTP) + hashed backup codes
- [x] Password reset via email token
- [x] Platform admin gated by allow-listed emails
- [ ] Periodic access review process (people/process)
- [ ] SSO enforced for enterprise tenants in production

## Change management
- [x] GitHub Actions CI for tests/builds
- [x] Image publish to GHCR + optional remote rollout
- [x] Alembic migrations versioned
- [ ] Mandatory code review policy on protected branches
- [ ] Change advisory record for production releases

## Logging & monitoring
- [x] Prometheus metrics + Grafana dashboards
- [x] Health/live/ready probes
- [x] Optional Sentry (`SENTRY_DSN`)
- [x] Public status page + incident timeline
- [ ] Centralized log retention policy (30/90 days)
- [ ] On-call runbook ownership — see `docs/ops/on-call-runbook.md`

## Data protection
- [x] Secrets via env / k8s Secret template (not in git)
- [x] Shop data export + delete APIs
- [x] Privacy / Terms pages
- [ ] Encryption at rest attestation for managed DB
- [ ] Backup restore drill schedule (documented evidence)

## Vendor management
- [ ] Inventory of subprocessors (Twilio, OpenAI, Stripe, hosting)
- [ ] DPA / BAA as applicable
- [ ] Annual vendor risk review

## Evidence to collect before audit
1. Access review spreadsheet (quarterly) — export via `GET /v1/platform/access-review`
2. Incident response tabletop notes — publish via `/platform` incidents + `/status`
3. Backup restore screenshots + timestamps — run `deploy/scripts/backup-drill.sh`
4. Production change tickets linked to PRs
5. Monitoring alert examples and acknowledgements

## Secrets on Kubernetes
- Prefer External Secrets (`values.externalSecrets.enabled=true`) or SealedSecret (`sealed-secret.example.yaml`)
- Never commit plaintext production credentials
