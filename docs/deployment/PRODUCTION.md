# Production Deployment Guide — AI Service Advisor (Phase 17)

## Overview

This document describes production deployment for **AI Service Advisor**: Docker images,
Compose stack, CI/CD (GitHub Actions), HTTPS, secrets, health checks, Prometheus/Grafana
monitoring, backups, and horizontal scaling.

## Architecture

```
Internet → Nginx (TLS :443) → Web (Next.js)
                           ↘ API (FastAPI × N) → Postgres
                                              → Redis
Prometheus ← /metrics (API) + exporters
Grafana ← Prometheus
Backup cron → /backups (pg_dump)
```

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- OpenSSL (for local cert generation) or a real cert (Let’s Encrypt)
- GitHub repository with Actions enabled (for CI/CD)
- At least 2 vCPU / 4 GB RAM for the full stack

## Quick start (production Compose)

```bash
# 1) Secrets
cp .env.production.example .env.production
# Edit JWT_SECRET, POSTGRES_PASSWORD, REDIS_PASSWORD, GRAFANA_ADMIN_PASSWORD

# 2) TLS certificates (dev/staging self-signed)
chmod +x deploy/scripts/*.sh
./deploy/scripts/generate-certs.sh

# 3) Build & start
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# 4) Verify
curl -fk https://localhost/health
curl -fk https://localhost/ready
curl -fsS http://localhost:9090/-/healthy   # Prometheus
curl -fsS http://localhost:3001/api/health  # Grafana
```

Open:

| Service    | URL |
|------------|-----|
| App (HTTPS)| https://localhost |
| API via proxy | https://localhost/api/health |
| Prometheus | http://localhost:9090 |
| Grafana    | http://localhost:3001 |

## Docker images

| Image | Dockerfile |
|-------|------------|
| API | `deploy/docker/Dockerfile.api` |
| Web | `deploy/docker/Dockerfile.web` |

API entrypoint waits for Postgres, runs `alembic upgrade head`, then starts Uvicorn workers.

## Health checks

| Path | Purpose |
|------|---------|
| `GET /live` | Liveness (process up) |
| `GET /ready` | Readiness (DB required; Redis optional via `READY_REQUIRE_REDIS`) |
| `GET /health` | Coarse status |
| `GET /metrics` | Prometheus scrape |

Compose and Docker `HEALTHCHECK` use `/live`. Orchestrators should gate traffic on `/ready` (HTTP 503 when not ready).

## Secrets

- Store runtime secrets in `.env.production` (gitignored pattern — never commit).
- Template: `.env.production.example`
- Required: `JWT_SECRET`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`
- Prefer a secrets manager (AWS Secrets Manager, GCP Secret Manager, Doppler, Vault) in real cloud deploys; inject as env vars at container start.
- Rotate `JWT_SECRET` carefully (invalidates sessions).

## HTTPS / TLS

- Nginx terminates TLS using `deploy/nginx/certs/fullchain.pem` + `privkey.pem`.
- Local/staging: `./deploy/scripts/generate-certs.sh`
- Production: replace with Let’s Encrypt (Certbot) or cloud-managed certificates; ACME webroot is prepared at `/var/www/certbot`.
- HTTP (:80) redirects to HTTPS; HSTS and security headers are enabled.

## Scaling

```bash
# Scale API replicas (Compose DNS load-balances `api:8000`)
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --scale api=3

# Or set API_REPLICAS / UVICORN_WORKERS in .env.production
```

Guidelines:

- Prefer **more API containers** over huge single-process workers for crash isolation.
- Keep Postgres/Redis as single primary instances unless you add managed HA.
- Nginx uses `least_conn` to API upstream.

## Monitoring

### Prometheus

- Config: `deploy/prometheus/prometheus.yml`
- Alerts: `deploy/prometheus/alerts.yml` (API down, 5xx rate, DB down, latency)
- Scrapes: `api:8000/metrics`, postgres-exporter, redis-exporter

### Grafana

- Provisioned datasource + **ASA Production Overview** dashboard
- Default login from `GRAFANA_ADMIN_*` env vars

## Backups

- Sidecar service `backup` runs `deploy/scripts/backup.sh` on a cron (`BACKUP_CRON`, default 03:00 UTC).
- Artifacts land in volume `asa_backups` as `asa_<db>_<timestamp>.sql.gz`.
- Retention: `BACKUP_KEEP_DAYS` (default 14).
- Restore:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm \
  -v asa-prod_asa_backups:/backups \
  backup /bin/sh /restore.sh /backups/asa_ai_service_advisor_YYYYMMDD.sql.gz
```

(Copy `restore.sh` into the image or mount it similarly to `backup.sh`.)

Manual backup:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backup /bin/sh /backup.sh
```

## CI/CD (GitHub Actions)

| Workflow | Trigger | Actions |
|----------|---------|---------|
| `.github/workflows/ci.yml` | PR / push | API pytest, web lint+build, Docker build (no push) |
| `.github/workflows/deploy.yml` | `main`/`master` push, `v*` tags, manual | Build & push API/Web to GHCR, then SSH `rollout.sh` |

Push to `main` (or `master`) builds images, tags `latest` + sha, and SSHs into the server to run `deploy/scripts/rollout.sh` (pull + up). Manual runs default to remote deploy; set `remote_deploy=false` to only push images.

### Required GitHub configuration

- Packages write permission (workflow already sets this).
- Optional repo variable `NEXT_PUBLIC_API_URL` for production web builds.
- Protect `main` and require CI green before merge.
- Secrets for auto remote deploy: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, optional `DEPLOY_PATH`.

### Rollout on a VM

Set `API_IMAGE` / `WEB_IMAGE` in `.env.production` to your GHCR images (see `.env.production.example`).

```bash
docker login ghcr.io
# Or rely on CI: bash deploy/scripts/rollout.sh
docker compose -f docker-compose.prod.yml --env-file .env.production pull
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

The server must be able to pull from GHCR (`docker login ghcr.io` once, or a read token in the Docker config).

## Security checklist

- [ ] Unique strong secrets in `.env.production`
- [ ] Real TLS certificates (not self-signed) in production
- [ ] Restrict Grafana/Prometheus ports to VPN or private network
- [ ] `/metrics` allowed only from internal CIDRs (nginx)
- [ ] API docs disabled when `ENVIRONMENT=production`
- [ ] Regular backups verified with restore drill
- [ ] Keep images patched (`docker compose pull`)

## Dev vs Prod Compose

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Local Postgres + Redis only |
| `docker-compose.prod.yml` | Full production stack |

## Troubleshooting

- **`/ready` 503**: check Postgres health; inspect `checks.database.error`.
- **Nginx SSL errors**: ensure certs exist under `deploy/nginx/certs/`.
- **Web can’t call API**: `NEXT_PUBLIC_API_URL` must match public HTTPS API prefix (`https://host/api`).
- **Migrations**: set `RUN_MIGRATIONS=true` (default) on API start; only one replica should migrate in large fleets (set others to `false` or use a migrate job).
