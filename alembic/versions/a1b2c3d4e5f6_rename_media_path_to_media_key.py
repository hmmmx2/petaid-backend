"""rename resources.media_path to media_key

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-06

Column kept as "media_path" in the DB; Python code accesses it as "media_key"
via a SQLAlchemy attribute alias.  The rename requires ACCESS EXCLUSIVE lock
which deadlocks with Railway blue-green deploys (old container holds DB
connections until the new one passes health check).
"""
from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # No-op: column stays "media_path" in DB; ORM exposes it as media_key.
    pass


def downgrade() -> None:
    pass
