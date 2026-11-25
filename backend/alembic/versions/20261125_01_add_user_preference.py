"""add user_preference (per-user display settings, e.g. Hebrew display)

Revision ID: 20261125_01
Revises: 20261123_02
Create Date: 2026-11-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261125_01"
down_revision = "20261123_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "user_preference" in sa.inspect(op.get_bind()).get_table_names():
        return  # Already created by the app's startup create_all().
    op.create_table(
        "user_preference",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("hebrew_display", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_preference")
