# Using Supabase as the PetAid database

PetAid's backend talks to Postgres through async SQLAlchemy + asyncpg. Supabase
*is* hosted Postgres, so no code changes are needed beyond the connection
string and a couple of pooler-safe settings (already wired in
`app/core/database.py`).

## 1. Create the project

1. Sign in at <https://supabase.com> → **New project**.
2. Choose a name, a strong **database password** (save it), and a region close
   to your Railway deployment region.
3. Wait for provisioning (~2 min).

## 2. Get the connection string

Supabase → **Project Settings → Database → Connection string → URI**. You'll see
three options:

| Mode | Host / Port | When to use |
|---|---|---|
| **Direct** | `db.<ref>.supabase.co:5432` | Long-lived servers, migrations, `alembic`. Limited connections. |
| **Session pooler** | `aws-0-<region>.pooler.supabase.com:5432` | Persistent app servers (Railway). Supports prepared statements. **Recommended for PetAid.** |
| **Transaction pooler** | `aws-0-<region>.pooler.supabase.com:6543` | Serverless / very high connection churn. No prepared statements. |

Copy the **Session pooler** URI. It looks like:

```
postgresql://postgres.abcdefghijklmnop:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

## 3. Rewrite it for asyncpg

Change the scheme from `postgresql://` to `postgresql+asyncpg://` and drop any
`?sslmode=...` query (we set SSL via settings):

```dotenv
# backend/.env
DATABASE_URL=postgresql+asyncpg://postgres.abcdefghijklmnop:YOUR-PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
DB_SSL=true            # optional — auto-enabled for *.supabase hosts
DB_STATEMENT_CACHE_SIZE=0
```

> `DB_STATEMENT_CACHE_SIZE=0` is required if you use the **transaction** pooler
> (6543); harmless on the session pooler/direct connection, so we leave it on.

If your password contains URL-special characters (`@ : / ? # [ ]`), percent-encode
them (e.g. `@` → `%40`).

## 4. Create the schema + seed

The seed script calls `Base.metadata.create_all`, so for a quick start you can
just run it against Supabase:

```bash
cd backend
python -m app.seed
```

For production-grade migrations use Alembic instead (recommended):

```bash
alembic revision --autogenerate -m "init"   # first time only
alembic upgrade head
python -m app.seed                            # demo data
```

Either path creates every table and inserts the two demo accounts:

- **Pet Owner:** `alwin@petaid.com` / `pet123`
- **Veterinary Expert:** `kavitha@petaid.com` / `vet123` (MFA `123456`)

## 5. Verify

```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health      # {"status":"ok"}
```

Then log in from the frontend.

## Deployment notes (Railway)

- Set `DATABASE_URL` (the asyncpg session-pooler URL), `JWT_SECRET`,
  `CORS_ORIGINS`, and `ENVIRONMENT=production` as Railway variables.
- Supabase's free tier sleeps after inactivity; the first request after idle
  may be slow. `pool_pre_ping=True` (already set) transparently reconnects.
- Keep `DB_POOL_SIZE` modest (≤10) — Supabase free tier caps total connections.

## Why not the Supabase client SDK / RLS?

PetAid's Assignment 3 design is an object-oriented FastAPI backend (AppController
singleton, AuthManager factory, Dashboard template-method, etc.). Using Supabase
purely as Postgres preserves that design 1:1. Supabase Auth + Row-Level Security
would replace the `AuthManager`/JWT layer and the SQLAlchemy data layer, which
would contradict the documented OO design. If you later want Supabase Storage for
real media files, that can be added behind the existing `MediaStorage` class
without touching anything else.
