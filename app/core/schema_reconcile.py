"""Idempotent, additive schema reconciliation run at application startup.

Background
----------
The PetAid models evolved after the first production deploy (a new
``donations.payment_method`` field, a switch of ``feedback`` from a polymorphic
``target_id`` / ``target_type`` pair to a single ``resource_id`` foreign key,
and a ``resources`` media column rename).  ``Base.metadata.create_all`` only
creates *missing tables* — it never adds columns to a table that already exists.
That left the live database missing columns the ORM now SELECTs, so
``/donations``, ``/first-aid`` and ``/feedback`` returned 500 even though the
deploy was green.

This module brings any drifted database back in line with the current models
using **additive-only** DDL:

* ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` — fast, catalog-only in
  PostgreSQL (no table rewrite, no ``ACCESS EXCLUSIVE`` rewrite lock), so it is
  safe under Railway blue-green deploys.
* A one-time backfill ``UPDATE`` from the legacy column when one exists.

Nothing is ever dropped or renamed, so the operation is safe to run on every
boot and on any environment (fresh or drifted).  Legacy columns are left in
place untouched — harmless dead weight.

Failures are swallowed with a warning: reconciliation must never block startup
or the health check (same discipline as the optional R2 integration).
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger("petaid.schema")


async def _existing_columns(conn, table: str) -> set[str]:
    rows = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    )
    return {r[0] for r in rows}


async def reconcile_schema() -> None:
    """Add any model columns missing from the live database (additive only)."""
    try:
        async with engine.begin() as conn:
            # --- resources.media_key (legacy column: media_path) ---------- #
            cols = await _existing_columns(conn, "resources")
            if cols and "media_key" not in cols:
                await conn.execute(
                    text("ALTER TABLE resources ADD COLUMN media_key VARCHAR(500)")
                )
                if "media_path" in cols:
                    await conn.execute(
                        text("UPDATE resources SET media_key = media_path "
                             "WHERE media_key IS NULL")
                    )
                logger.info("Reconciled resources.media_key")

            # --- donations.payment_method (new field, no legacy) ---------- #
            cols = await _existing_columns(conn, "donations")
            if cols and "payment_method" not in cols:
                await conn.execute(
                    text("ALTER TABLE donations ADD COLUMN payment_method VARCHAR(40)")
                )
                logger.info("Reconciled donations.payment_method")

            # --- feedback.resource_id (legacy column: target_id) ---------- #
            cols = await _existing_columns(conn, "feedback")
            if cols and "resource_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE feedback ADD COLUMN resource_id UUID")
                )
                if "target_id" in cols:
                    await conn.execute(
                        text("UPDATE feedback SET resource_id = target_id "
                             "WHERE resource_id IS NULL")
                    )
                logger.info("Reconciled feedback.resource_id")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Schema reconciliation skipped (%s): %s", type(exc).__name__, exc
        )
