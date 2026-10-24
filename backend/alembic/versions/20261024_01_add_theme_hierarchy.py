"""add theme hierarchy fields

Revision ID: 20261024_01
Revises: 20260614_01
Create Date: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20261024_01"
down_revision = "20260614_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("theme", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("theme", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column(
        "theme",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_theme_parent_id",
        "theme",
        "theme",
        ["parent_id"],
        ["id"],
    )
    op.create_index("ix_theme_parent_id", "theme", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_theme_parent_id", table_name="theme")
    op.drop_constraint("fk_theme_parent_id", "theme", type_="foreignkey")
    op.drop_column("theme", "sort_order")
    op.drop_column("theme", "parent_id")
    op.drop_column("theme", "description")
