# PetAid — Backend (FastAPI)

PetAid is a warm, light-mode web application for **pet first-aid guidance and veterinary support**.
This repository is the **backend API**; the user interface lives in a separate repo,
[`petaid-frontend`](https://github.com/hmmmx2/petaid-frontend) (Next.js).

> Built for **SWE30003 — Software Architectures & Design, Assignment 3**. The object-oriented domain
> model from Assignment 2 is implemented here as a layered FastAPI service with a PostgreSQL database.

- **Framework:** FastAPI · async SQLAlchemy 2.0 · asyncpg
- **Database:** PostgreSQL 16 (hosted on **Supabase**; runs on local Postgres too)
- **Auth:** JWT (access + refresh) · bcrypt password hashing · RFC-6238 TOTP MFA for vets · RBAC
- **Real-time:** WebSockets (live chat: messages, typing, presence, read receipts)
- **Migrations:** Alembic (or one-shot `python -m app.seed` for dev)

## Architecture at a glance

```
Browser ──HTTPS──►  petaid-frontend (Next.js)  ──HTTPS/JSON──►  petaid-backend (FastAPI)  ──►  PostgreSQL (Supabase)
                                                  ◄──WebSocket──   /api/v1/ws/chat
```

The frontend never talks to the database directly — it only calls this API. This backend owns all
domain logic, validation, RBAC, rate limiting and persistence.

---

## 1. Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| **Python** | 3.11 or newer (3.12 used in dev) | `python --version` |
| **A PostgreSQL database** | 14+ | Either a free [Supabase](https://supabase.com) project **or** local Postgres (Docker provided) |
| **Git** | any | to clone |
| *(optional)* **Docker Desktop** | any | only if you want a local Postgres via `docker compose` |

Development & testing platform: **Windows 11 + PowerShell**, editor **VS Code**. The commands below
are PowerShell; the equivalent macOS/Linux commands are noted where they differ.

---

## 2. Clone the repository

```powershell
git clone https://github.com/hmmmx2/petaid-backend.git
cd petaid-backend
```

## 3. Create a virtual environment & install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux:  source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure environment variables

```powershell
Copy-Item .env.example .env         # macOS/Linux:  cp .env.example .env
```

Open `.env` and set the values. The two **required** ones are `DATABASE_URL` and `JWT_SECRET`.

#### `DATABASE_URL` — pick ONE source of Postgres

**Option A — Supabase (recommended).** In the Supabase dashboard go to
**Project Settings → Database → Connection string → URI → Session pooler**, then rewrite the scheme
to `postgresql+asyncpg://` (full walkthrough in [`SUPABASE.md`](./SUPABASE.md)):

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<DB-PASSWORD>@aws-1-<region>.pooler.supabase.com:5432/postgres
DB_SSL=true
```

**Option B — local Postgres via Docker** (no Supabase account needed):

```powershell
docker compose up -d db             # starts Postgres on localhost:5432
```
```dotenv
DATABASE_URL=postgresql+asyncpg://petaid:petaid@localhost:5432/petaid
```

#### `JWT_SECRET` — generate a strong random value

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Paste the output into `JWT_SECRET=...`. Also confirm `CORS_ORIGINS` includes your frontend origin
(default already allows `http://localhost:3000`).

## 5. Create the database schema + seed demo data

`app.seed` creates every table (`Base.metadata.create_all`) **and** inserts the demo accounts and
sample content. It is idempotent — safe to re-run.

```powershell
python -m app.seed
```

You should see it print the seeded accounts and a current TOTP code for the vet.

> **Production note:** for a real deployment use Alembic migrations instead:
> `alembic upgrade head` (the Docker image runs this automatically on start).

## 6. Run the API

```powershell
uvicorn app.main:app --reload
```

- API base: <http://localhost:8000>
- Health check: <http://localhost:8000/health> → `{"status":"ok"}`
- Interactive API docs (Swagger UI): <http://localhost:8000/docs>

## 7. Demo accounts (created by the seed)

| Role | Email | Password | MFA |
| --- | --- | --- | --- |
| **Pet Owner** | `alwin@petaid.com` | `pet123` | none |
| **Veterinary Expert** | `kavitha@petaid.com` | `vet123` | TOTP — a current 6-digit code is printed when the seed runs (dev secret is fixed for reproducibility) |

Log in from the [frontend](https://github.com/hmmmx2/petaid-frontend), or hit the API directly via `/docs`.

---

## Database design

The full database design — entity-relationship diagram, data dictionary, and the
object-oriented→relational mapping rationale — lives in **[`docs/database/`](./docs/database/)**:

- [`docs/database/DATABASE.md`](./docs/database/DATABASE.md) — ERD + data dictionary + design notes (for the report)
- [`docs/database/schema.sql`](./docs/database/schema.sql) — runnable PostgreSQL DDL (16 tables)

To recreate the schema in a fresh Supabase project for the report, paste `schema.sql` into the
Supabase **SQL Editor**, then export the diagram from **Database → Schema Visualizer**.

## API surface (v1)

All routes are under `/api/v1`. Full, always-current spec at `GET /openapi.json` (and `/docs`).

| Area | Example endpoints | Auth |
| --- | --- | --- |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/verify-email`, `GET /auth/me` | public / bearer |
| Dashboard | `GET /dashboard` (role-aware aggregate + RBAC grants) | bearer |
| Pets | `GET/POST /pets`, `PATCH/DELETE /pets/{id}`, `GET /pet-types` | bearer |
| First aid | `GET /first-aid` | public/bearer |
| Resources | `GET/POST /resources`, `POST /resources/{id}/publish` | bearer (vet) |
| Quizzes | `GET /quizzes`, `GET /quizzes/{id}`, `POST /quizzes/{id}/attempts`, `GET /quizzes/attempts` | bearer |
| Inquiries | `GET/POST /inquiries`, `POST /inquiries/{id}/respond`, `/close` | bearer |
| Chats | `GET/POST /chats`, `POST /chats/{id}/join`, `/messages`, `/read`, `/close` | bearer |
| Donations | `GET/POST /donations` | bearer |
| Feedback | `GET/POST /feedback` | bearer |
| Real-time | `WS /api/v1/ws/chat?token=<access JWT>` — message / typing / presence / read frames | token query param |
| Meta | `GET /health` | public |

## Project layout

```
app/
├── main.py                FastAPI app factory · CORS · security headers · error handlers · /health
├── core/
│   ├── config.py          Pydantic Settings (.env-driven; fails fast on weak prod config)
│   ├── database.py        Async engine + session + Base (Supabase/pooler-aware)
│   ├── security.py        JWT encode/decode + bcrypt hashing
│   ├── totp.py            RFC-6238 TOTP (stdlib only) for vet MFA
│   └── rate_limit.py      In-memory anti-spam limiter
├── models/                SQLAlchemy ORM — the domain entities (source of truth for the DB schema)
├── schemas/               Pydantic request/response DTOs (the public API contract)
├── domain/                AppController (singleton), AuthManager, EventBus, RBAC permissions, exceptions
├── services/              Aggregation logic kept out of routers (e.g. dashboard)
├── realtime/              ConnectionManager (in-memory WS registry + presence)
├── api/v1/                Routers: auth, dashboard, pets, pet_types, resources, first_aid,
│                          quizzes, inquiries, chats, donations, feedback, ws
└── seed.py                Idempotent schema-create + demo seed
docs/database/             DATABASE.md (ERD + data dictionary) + schema.sql (DDL)
alembic/                   Production migrations (async engine)
Dockerfile · railway.toml · docker-compose.yml · SUPABASE.md
```

## Environment variables

| Var | Required | Default | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | **yes** | – | `postgresql+asyncpg://…` — must use the **asyncpg** driver |
| `JWT_SECRET` | **yes** | – | ≥32 random chars (enforced in production) |
| `ENVIRONMENT` | no | `development` | `production` hides `/docs` & enforces strong secrets/CORS |
| `CORS_ORIGINS` | prod | `http://localhost:3000` | Comma-separated allow-list; include your Vercel URL |
| `JWT_ALGORITHM` | no | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | `14` | |
| `DB_SSL` | no | auto for Supabase | force TLS to the DB |
| `DB_STATEMENT_CACHE_SIZE` | no | `0` | keep `0` behind Supabase poolers |
| `RATE_LIMIT_ENABLED` | no | `true` | disable only in controlled tests |

## Verifying it works (assignment evidence)

```powershell
# 1. Health
curl http://localhost:8000/health                      # {"status":"ok"}

# 2. Log in as the pet owner (no MFA)
curl -X POST http://localhost:8000/api/v1/auth/login `
     -H "Content-Type: application/json" `
     -d '{"email":"alwin@petaid.com","password":"pet123"}'
# → returns {access_token, refresh_token, role:"pet_owner", ...}

# 3. Browse every endpoint interactively at /docs
```

## Deployment — Railway + Supabase

1. Create the Supabase project and copy its **session-pooler** connection string (see `SUPABASE.md`).
2. Create a Railway project, add this repo as a service (it auto-detects `railway.toml` + `Dockerfile`).
3. Set Railway variables: `DATABASE_URL` (asyncpg form), `JWT_SECRET`, `ENVIRONMENT=production`,
   `CORS_ORIGINS=https://<your-frontend>.vercel.app`.
4. Deploy. The container runs `alembic upgrade head` before starting Uvicorn.
5. Seed once from the Railway shell (or rely on Alembic + manual data): `python -m app.seed`.

> Railway runs a single long-lived process, so WebSockets work out of the box. The in-memory
> `ConnectionManager`/presence is correct for a single instance; horizontal scaling would add Redis
> pub/sub behind the same interface (documented, not required for this assignment).

## Coding standard

Python code follows **[PEP 8](https://peps.python.org/pep-0008/)** and
**[PEP 257](https://peps.python.org/pep-0257/)** (docstring conventions), with type hints throughout
(PEP 484). Layering (routers → domain/services → models) and the design patterns used
(Singleton controller, Observer event bus, Adapter payment processor, Repository-style data access)
are described in [`DESIGN.md`](./DESIGN.md).
