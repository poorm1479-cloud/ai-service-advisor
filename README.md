# AI Service Advisor

Multi-tenant SaaS platform for independent auto repair shops. Helps shops manage customers, vehicles, appointments, AI-assisted conversations (SMS/voice), workflows, revenue insights, and shop knowledge — with strong tenant isolation.

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js · React · TypeScript · Tailwind |
| API | FastAPI · Clean Architecture |
| DB | PostgreSQL (RLS on shop-scoped tables) |
| Cache / queue | Redis |
| Auth | JWT access + opaque refresh tokens (hashed) |
| AI | Modular providers: heuristic · OpenAI · Ollama (with fallbacks) |

## Repository layout

```
apps/
  api/          FastAPI backend
  web/          Next.js frontend
deploy/         Docker, Kubernetes, monitoring
docs/           Architecture ADRs and ops guides
scripts/        DB setup and automation
testdata/       Sample import files (synthetic)
```

### Backend modules

```
apps/api/app/
  domain/           entities, enums, ports, exceptions
  application/      use cases / services
  infrastructure/   SQLAlchemy, repos, security, UoW
  api/              routers, schemas, deps
  memory/           shop knowledge & memory
  plugins/          advisor and feature plugins
  main.py
```

## Roles

- `owner`
- `manager`
- `service_advisor`
- `mechanic`

Registration creates a **Shop** and an **Owner** membership.

## Prerequisites

- Node.js + [pnpm](https://pnpm.io)
- Python 3.11+
- PostgreSQL
- Redis (optional for some features)

## Quick start

### 1. Environment

```bash
cp .env.example .env
# Edit secrets and connection strings as needed
```

Never commit `.env`. Runtime data under `apps/api/storage/` is also gitignored.

### 2. Database

```bash
# once — create role/db (example postgres password: root)
psql -U postgres -h 127.0.0.1 -f scripts/setup_db.sql

cd apps/api
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
```

### 3. API

```bash
cd apps/api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

### 4. Web

```bash
pnpm install
pnpm dev:web
```

| Surface | URL |
|---|---|
| Home | http://localhost:3000 |
| Register | http://localhost:3000/register |
| Login | http://localhost:3000/login |
| Shop dashboard | http://localhost:3000/dashboard |
| Admin login | http://localhost:3000/admin/login → `POST /v1/auth/admin/login` (default `RyanChen` / `Albert824@`) |
| Admin console | http://localhost:3000/admin (`PLATFORM_ADMIN_USERNAMES`, `account_type=platform_admin`) |
| API docs | http://localhost:8000/docs |

## Tests

```bash
cd apps/api
.\.venv\Scripts\activate
pytest -q
```

Or from the repo root:

```bash
pnpm test:api
```

## Auth API (core)

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/auth/register` | Create shop + owner (`account_type=shop`) |
| POST | `/v1/auth/login` | Shop username/password (rejects platform admins) |
| POST | `/v1/auth/admin/login` | Platform admin only (no shop) |
| POST | `/v1/auth/refresh` | Rotate refresh token |
| POST | `/v1/auth/logout` | Revoke refresh |
| GET | `/v1/auth/me` | Bearer access (shop accounts) |
| CRUD | `/v1/customers` | Shop-isolated customers |

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
