# RatchetHub

Multi-tenant SaaS for independent auto repair shops. Manage customers, vehicles, appointments, AI SMS/voice conversations, workflows, billing, revenue intelligence, and shop knowledge — with shared-schema tenancy and PostgreSQL RLS.

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js 15 · React 19 · TypeScript · Tailwind |
| API | FastAPI modular monolith · Clean Architecture |
| DB | PostgreSQL 16 (RLS on shop-scoped tables) |
| Cache / queue | Redis 7 |
| Auth | JWT access + opaque refresh · phone/email OTP · MFA (TOTP) |
| AI | Modular providers: OpenAI · Ollama · heuristic (with fallbacks) |
| Comms | Twilio SMS & Voice (fake providers for local) |
| Billing | SaaS plans (`free` / `pro` / `enterprise`) · Stripe-ready |

## Repository layout

```
apps/
  api/          FastAPI backend
  web/          Next.js frontend
deploy/         Docker, Nginx, Helm, Prometheus, Grafana
docs/           ADRs, deployment, ops, compliance
scripts/        DB bootstrap and smoke checks
```

### Backend packages (`apps/api/app/`)

Core: `domain/`, `application/`, `infrastructure/`, `api/`, `auth/`, `tenancy/`, `identity/`

Product: `sms/`, `voice/`, `telephony/`, `scheduling/`, `workflows/`, `agents/`, `memory/`, `learning/`, `revenue/`, `revenue_intel/`, `marketing/`, `analytics/`, `import_engine/`, `integrations/`, `mcp_hub/`, `enterprise/`, `saas/`, `admin/`, `dashboard/`, `shop_setup/`

## Capabilities

- **Shop ops** — customers, vehicles, walk-ins, appointments, team, setup wizard
- **AI communications** — SMS inbox, voice calls, AI agents, voice notes
- **Automation** — workflows, marketing, import engine
- **Insights** — analytics, revenue, revenue intelligence, shop memory / knowledge
- **Platform** — billing & quotas, enterprise SSO, external integrations, MCP hub
- **Admin console** — shops, users, AI usage, Twilio numbers, system health, tokens

## Roles

Shop principals:

| Role | Notes |
|---|---|
| `owner` | Shop owner (created at registration) |
| `staff` | Shop staff |
| `ai_agent` | AI agent principal |

Legacy job titles (`manager`, `service_advisor`, `mechanic`, …) still normalize to `staff`.

Platform: `account_type=platform_admin` (separate admin login).

## Prerequisites

- Node.js + [pnpm](https://pnpm.io) (`packageManager` pinned in root `package.json`)
- Python 3.11+
- PostgreSQL 16
- Redis 7 (optional for some features; Compose provides it)

## Quick start

### 1. Environment

```bash
cp .env.example .env
# Edit secrets and connection strings as needed
```

Never commit `.env`. Runtime data under `apps/api/storage/` is gitignored.

For production templates see `.env.production.example`.

### 2. Databases (optional Docker)

```bash
docker compose up -d
```

Or create the role/DB once:

```bash
psql -U postgres -h 127.0.0.1 -f scripts/setup_db.sql
```

### 3. API

```bash
cd apps/api
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

From the repo root you can also use:

```bash
pnpm dev:api
```

### 4. Web

```bash
pnpm install
pnpm dev:web
```

| Surface | URL |
|---|---|
| Home / pricing | http://localhost:3000 |
| Register | http://localhost:3000/register |
| Login | http://localhost:3000/login |
| Shop dashboard | http://localhost:3000/dashboard |
| Admin login | http://localhost:3000/admin/login |
| Admin console | http://localhost:3000/admin |
| API docs | http://localhost:8000/docs |

Default platform admin bootstrap (dev): `PLATFORM_ADMIN_USERNAMES` / `PLATFORM_ADMIN_BOOTSTRAP_PASSWORD` in `.env` (example: `admin` / `admin`).

## Tests

```bash
cd apps/api
.\.venv\Scripts\activate
pytest -q
```

Or:

```bash
pnpm test:api
```

## Auth API (core)

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/auth/register` | Create shop + owner (`account_type=shop`) |
| POST | `/v1/auth/login` | Shop credentials (rejects platform admins) |
| POST | `/v1/auth/admin/login` | Platform admin only |
| POST | `/v1/auth/refresh` | Rotate refresh token |
| POST | `/v1/auth/logout` | Revoke refresh |
| GET | `/v1/auth/me` | Bearer access (shop accounts) |

Additional auth surfaces (OTP, MFA, password reset) live under `/v1/auth/*`. Shop data routes are tenant-isolated (e.g. `/v1/customers`).

## Production

See [docs/deployment/PRODUCTION.md](docs/deployment/PRODUCTION.md) for Docker Compose, HTTPS, secrets, monitoring, and backups.

```bash
pnpm prod:up
pnpm prod:down
```

## Documentation

- Architecture decisions: [`docs/architecture/`](docs/architecture/)
- Deployment: [`docs/deployment/`](docs/deployment/)
- Ops / compliance: [`docs/ops/`](docs/ops/), [`docs/compliance/`](docs/compliance/)
