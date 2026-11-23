"""add hebrew_mode to lesson texts and content versions

Revision ID: 20261123_01
Revises: 20261024_01
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20261123_01"
down_revision = "20261024_01"
branch_labels = None
depends_on = None


LESSON_HEBREW_MODE_COLUMNS = (
    "corrected_transcript_hebrew_mode",
    "edited_transcript_hebrew_mode",
    "summary_hebrew_mode",
)


def upgrade() -> None:
    # Existing content is transliterated: server_default backfills 'translit'.
    op.add_column(
        "content_version",
        sa.Column("hebrew_mode", sa.String(), nullable=False, server_default="translit"),
    )
    for column_name in LESSON_HEBREW_MODE_COLUMNS:
        op.add_column(
            "lesson",
            sa.Column(column_name, sa.String(), nullable=False, server_default="translit"),
        )


def downgrade() -> None:
    for column_name in reversed(LESSON_HEBREW_MODE_COLUMNS):
        op.drop_column("lesson", column_name)
    op.drop_column("content_version", "hebrew_mode")
