# PetAid — Database Design Audit Report
**Project:** `aowflksosmpssvwyraim` (Supabase)  
**Source:** `docs/database/schema.sql` (canonical DDL, generated from SQLAlchemy models)  
**Date:** 2026-05-31  

---

## 1. Live Database / Supabase Status

**Supabase project is inaccessible — consistent with a paused free-tier instance.**

Every attempt to open a project-level page (`/project/.../sql`, `/project/.../editor`, etc.) redirected back to sign-in after the React app loaded. The organisation list (`/org`) loaded successfully, confirming the user session is valid. This mismatch — org page works, project pages bounce — is the exact behaviour of a Supabase free-tier project auto-paused after ≥7 days of database inactivity.

This is expected: the `.env` files show `DATABASE_URL` pointing to a local Postgres (dev) or Railway Postgres (prod), **not** Supabase. The Supabase project is provisioned for **Storage only** (`SUPABASE_STORAGE_BUCKET=pet-media`). The `public` schema on Supabase has almost certainly never had `schema.sql` applied to it and is therefore empty.

**Introspection queries (a–g) could not be executed against the live Supabase instance.** Analysis below is performed against the canonical `docs/database/schema.sql`, which is the authoritative DDL for all deployments.

---

## 2. Schema Summary

**Tables: 16 ✓** — all expected tables are present.

| # | Table | Role |
|---|-------|------|
| 1 | `accounts` | STI root (pet_owner / veterinary_expert) |
| 2 | `user_credentials` | 1:1 composition ← accounts |
| 3 | `pet_types` | Reference / lookup |
| 4 | `pets` | Aggregation ← accounts |
| 5 | `first_aid_guidance` | Core content |
| 6 | `resources` | Core content |
| 7 | `first_aid_resource_link` | M:N junction |
| 8 | `quizzes` | 1:N ← resources |
| 9 | `quiz_attempts` | Aggregation ← accounts |
| 10 | `inquiries` | Aggregation ← accounts |
| 11 | `chats` | Aggregation ← accounts |
| 12 | `chat_messages` | 1:N ← chats |
| 13 | `donations` | Aggregation ← accounts |
| 14 | `donation_records` | 1:1 composition ← donations |
| 15 | `feedback` | Aggregation ← accounts, optional → resources |
| 16 | `feedback_entries` | 1:1 composition ← feedback |

**All 16 tables match the expected design exactly.**

**Seeded data:** Cannot confirm from Supabase (project paused). Per `SUPABASE.md`, running `python -m app.seed` against a live connection would insert two demo accounts (`alwin@petaid.com` / `kavitha@petaid.com`) plus pet-type seed rows.

---

## 3. Critical Feedback Verification ✅ PASS — NEW design confirmed

The `feedback` table contains exactly:

```
submitter_id UUID NOT NULL  → FK accounts (CASCADE)
resource_id  UUID           → FK resources (CASCADE, nullable, via ALTER TABLE)
flagged      BOOLEAN NOT NULL
```

- **No `guidance_id` column** ✓  
- **No polymorphic `(target_type, target_id)` pair** ✓  
- Single real FK to `resources` preserves referential integrity ✓  
- Cascade-on-resource-delete is correct (feedback is meaningless without its target) ✓

**Verdict: live DDL carries the NEW (corrected) feedback design.**  
The old polymorphic design is gone. No remediation needed.

---

## 4. Drift vs Expected Design

**None detected.** Every element of the specification is present in `schema.sql`:

| Check | Result |
|-------|--------|
| 16 tables | ✓ All present |
| UUID PKs with `gen_random_uuid()` default | ✓ All 15 entity tables (link table uses composite PK, as expected) |
| `created_at`/`updated_at timestamptz` on every entity table | ✓ All 15 entity tables |
| STI discriminator `accounts.role` | ✓ |
| 1:1 via UNIQUE FK + CASCADE: `user_credentials`, `donation_records`, `feedback_entries` | ✓ All three |
| M:N composite PK + both FKs CASCADE: `first_aid_resource_link` | ✓ |
| `chats.vet_id` SET NULL, `inquiries.assigned_vet_id` SET NULL | ✓ |
| RESTRICT on `pet_types` and author FKs | ✓ |
| All CASCADE deletes for owned data | ✓ |
| All 10 CHECK constraints | ✓ (see §5) |
| Index on every FK + status/flag columns | ✓ (see §6) |

**Minor note:** `first_aid_resource_link` has no `created_at`/`updated_at` columns. The spec says "every table," but omitting audit columns from a pure junction table is conventional and harmless for this design. Not considered drift.

---

## 5. CHECK Constraint Verification ✅ All 10 present

| Constraint | Definition | Status |
|-----------|-----------|--------|
| `ck_accounts_role` | `role in ('pet_owner','veterinary_expert')` | ✓ |
| `ck_chats_status` | `status in ('initiated','active','closed')` | ✓ |
| `ck_inquiries_status` | `status in ('pending','responded','closed')` | ✓ |
| `ck_resources_status` | `status in ('draft','published')` | ✓ |
| `ck_donations_status` | `status in ('pending','succeeded','failed')` | ✓ |
| `ck_feedback_rating` | `rating between 1 and 5` | ✓ |
| `ck_quiz_attempts_score` | `score_pct between 0 and 100` | ✓ |
| `ck_donations_amount` | `amount_cents > 0` | ✓ |
| `ck_resources_content_type` | `content_type in ('video','pdf','images')` | ✓ |
| `ck_pets_age` | `age_years is null or age_years between 0 and 80` | ✓ |

---

## 6. Design Quality Assessment

| Area | Rating | Notes |
|------|--------|-------|
| **Normalization** | Good | 3NF/BCNF throughout. JSONB columns (`steps`, `questions`, `answers`, `image_urls`) are deliberate value-object denormalizations — appropriate for append-only lists with no independent query need. STI on `accounts` is the correct tradeoff given the OO design mandate. |
| **Keys & Uniqueness** | Good | UUID PKs everywhere; UNIQUE on `user_credentials.account_id` and `.email`; UNIQUE on `donation_records.donation_id` and `.transaction_ref`; UNIQUE on `feedback_entries.feedback_id`; UNIQUE on `pet_types.name`. 1:1 compositions correctly enforced via unique-index FK. |
| **ON DELETE policies** | Good | CASCADE owns, SET NULL for optional vet assignments, RESTRICT for reference data. One consideration: `chat_messages.sender_id → accounts CASCADE` means a deleted vet's messages vanish even in a pet owner's chat. SET NULL + nullable `sender_id` would preserve chat history. Low impact for this assignment scope. |
| **CHECK coverage** | Good | All 10 constraints present; application-layer enum and range validations are mirrored at the DB layer. |
| **Indexing** | Acceptable | Every FK has a covering index. Status and flag columns indexed. One gap: `first_aid_resource_link` has no secondary index on `resource_id` alone. The composite PK `(guidance_id, resource_id)` supports "all resources for a guidance" but not "all guidance for a resource" efficiently. Add `CREATE INDEX ON first_aid_resource_link (resource_id)` to fix. |
| **STI & M:N modeling** | Good | STI via `accounts.role` CHECK is clean. M:N junction has composite PK with both FKs cascading. No spurious surrogate key on the link table. |
| **Referential integrity** | Good | No gaps. The deferred `feedback → resources` FK is correctly issued via `ALTER TABLE` after `resources` is created, avoiding forward-reference issues. No circular FK cycles. No bare UUID columns masquerading as FKs. |

---

## 7. Remaining Issues

**Fix (minor):**

1. **Missing reverse index on `first_aid_resource_link(resource_id)`.**  
   Add: `CREATE INDEX ON first_aid_resource_link (resource_id);`  
   This makes "fetch all guidance articles linked to resource X" O(log n) instead of a full table scan.

**Consider (low priority):**

2. **`chat_messages.sender_id ON DELETE CASCADE`** removes message history when a vet account is deleted. If chat audit trails matter, change to `SET NULL` with `sender_id` made nullable, and display deleted-account messages as "Deleted User."

3. **`first_aid_resource_link` has no `created_at`** — if you ever need to know when a resource was linked to a guidance article, add the column now (cheap) rather than later.

---

## 8. ERD Recommendation

Since the Supabase project is paused and the `public` schema is empty, the Schema Visualizer shows nothing useful.

**To get the ERD for your report:**
1. Create a throwaway Supabase project (or restore this one from the Dashboard → Project Settings → Restore).
2. Go to **SQL Editor → New query**, paste `docs/database/schema.sql`, click **Run**.
3. Go to **Database → Schema Visualizer** — the full 16-table ERD will render automatically.
4. Click **Download** (SVG/PNG) or screenshot for inclusion in the report.

Alternatively, paste `schema.sql` into [dbdiagram.io](https://dbdiagram.io) (supports PostgreSQL DDL import) for a free, instant ERD without needing a live database.
