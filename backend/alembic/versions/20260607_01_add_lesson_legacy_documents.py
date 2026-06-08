"""add lesson legacy document fields

Revision ID: 20260607_01
Revises: 20260604_01
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260607_01"
down_revision = "20260604_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lesson", sa.Column("pdf_files", sa.JSON(), nullable=True))
    op.add_column("lesson", sa.Column("legacy_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("lesson", "legacy_url")
    op.drop_column("lesson", "pdf_files")
