"""rename resources.media_path to media_key

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-06

The column is renamed from ``media_path`` (a loose URL placeholder) to
``media_key`` (a typed R2 object key) to reflect the new direct-upload
architecture.  All existing rows are preserved — the column value is carried
over as-is; any non-null legacy values will simply return themselves as the
fallback ``media_url`` until overwritten via the new upload flow.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Idempotent: only rename if media_path still exists (not already renamed).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'media_path'
            ) THEN
                ALTER TABLE resources RENAME COLUMN media_path TO media_key;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'media_key'
            ) THEN
                ALTER TABLE resources RENAME COLUMN media_key TO media_path;
            END IF;
        END $$;
    """)
