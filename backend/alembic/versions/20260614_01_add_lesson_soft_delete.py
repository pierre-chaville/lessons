"""add lesson soft delete fields

Revision ID: 20260614_01
Revises: 20260608_01
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260614_01"
down_revision = "20260608_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lesson", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("lesson", sa.Column("deleted_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lesson", "deleted_by")
    op.drop_column("lesson", "deleted_at")
