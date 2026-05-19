# petaid-backend

FastAPI service powering [PetAid](https://github.com/) — a warm, light-mode web app for pet first-aid guidance.

- **Framework:** FastAPI · async SQLAlchemy 2 · asyncpg
- **Auth:** JWT (access + refresh) · bcrypt-hashed passwords
- **Migrations:** Alembic
- **Database:** PostgreSQL 16
- **Deploys to:** Railway (Docker)

The frontend lives in a separate repo: **petaid-frontend** (Next.js 14, deploys to Vercel). The two communicate only over HTTPS.

## Quick start (local)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: set DATABASE_URL and JWT_SECRET

# Option A — spin up a local Postgres via docker-compose
docker compose up -d db

# Option B — point DATABASE_URL at any Postgres you already have

# First-time migration
alembic revision --autogenerate -m "init"
alembic upgrade head

# Seed Alwin's demo data (idempotent)
python -m app.seed

# Run the API
uvicorn app.main:app --reload
# → http://localhost:8000
# → interactive docs at /docs
```

**Demo login:** `alwin@petaid.local` / `petaid-demo-2026`

### One-shot via Docker Compose

```powershell
docker compose up --build
# API on :8000, Postgres on :5432
```

## Project layout

```
app/
├── main.py              FastAPI app factory · CORS · /health
├── core/
│   ├── config.py        Pydantic Settings (.env-driven)
│   ├── database.py      Async engine + session + Base
│   └── security.py      JWT encode/decode + bcrypt hashing
├── models/              SQLAlchemy models (User, Pet, Quiz, Chat, Resource, Readiness, Reminder)
├── schemas/             Pydantic request/response DTOs — this is the public contract
├── api/
│   ├── deps.py          DbDep, CurrentUserDep
│   └── v1/              auth, pets, dashboard routers
├── services/
│   └── dashboard.py     Aggregation logic (kept out of routers)
└── seed.py              Idempotent demo seed
alembic/                 Migrations (env.py wired to async engine)
Dockerfile               Production image · non-root · runs alembic on start
railway.toml             Railway build/deploy config
docker-compose.yml       Local Postgres + API for `docker compose up`
```

## API surface (v1)

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET`  | `/health` | – | Liveness probe (Railway healthcheck) |
| `POST` | `/api/v1/auth/register` | – | Create user, returns token pair |
| `POST` | `/api/v1/auth/login` | – | Email + password → token pair |
| `POST` | `/api/v1/auth/refresh` | – | Exchange refresh token for a fresh pair |
| `GET`  | `/api/v1/dashboard` | bearer | Aggregated dashboard payload |
| `GET`  | `/api/v1/pets` | bearer | List the current user's pets |
| `POST` | `/api/v1/pets` | bearer | Create a pet |
| `DELETE` | `/api/v1/pets/{id}` | bearer | Delete a pet |

The OpenAPI schema is auto-generated; consume it at `GET /openapi.json` (e.g. with [openapi-typescript](https://github.com/drwpow/openapi-typescript) in the frontend).

## Environment variables

| Var | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@host:5432/db` — **must use the asyncpg driver** |
| `JWT_SECRET` | yes | ≥48 random chars. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_ALGORITHM` | no | Defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Defaults to 30 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | Defaults to 14 |
| `CORS_ORIGINS` | yes in prod | Comma-separated; must include your Vercel frontend URL |
| `ENVIRONMENT` | no | `production` hides `/docs` |

## Deployment — Railway

1. Create a Railway project and attach a Postgres plugin.
2. Railway injects `DATABASE_URL` using the `postgresql://` scheme. Override it to `postgresql+asyncpg://...` (same host/user/pass), or set it manually from the Postgres plugin's connection variables.
3. Connect this repo as a service. Railway detects `railway.toml` + `Dockerfile`.
4. Set `JWT_SECRET`, `CORS_ORIGINS=https://<your-frontend>.vercel.app`, `ENVIRONMENT=production`.
5. Deploy. The container runs `alembic upgrade head` before starting Uvicorn.
6. Once deployed, run seed from Railway's shell once: `python -m app.seed`.

## Best practices baked in

- Async all the way (SQLAlchemy async + asyncpg + native async routes).
- Pydantic v2 settings — secrets only via env, never via code.
- bcrypt password hashing via `passlib`; tokens never log plaintext.
- Service-layer aggregation (`app/services/`) keeps routers thin.
- Migrations run on container start; never edit the DB schema directly.
- Non-root Docker user, slim base image, multi-line CMD with `$PORT` for Railway.
- Explicit CORS allow-list; no wildcard in production.
- Idempotent seed — safe to re-run.

## Next steps (not yet implemented)

- pytest + httpx integration tests
- Rate limiting (slowapi or starlette-limiter)
- Structured logging (structlog) + request IDs
- WebSocket chat threads
- Quiz scoring endpoint
- Emergency First Aid step-by-step engine
