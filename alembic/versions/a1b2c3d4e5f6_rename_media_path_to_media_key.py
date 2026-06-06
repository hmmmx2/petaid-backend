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
    op.alter_column("resources", "media_path", new_column_name="media_key")


def downgrade() -> None:
    op.alter_column("resources", "media_key", new_column_name="media_path")
