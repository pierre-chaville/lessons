"""add rag chunks and lesson hash columns

Revision ID: 20260604_01
Revises: 20260506_01
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260604_01"
down_revision = "20260506_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lesson", sa.Column("rag_summary_current_hash", sa.String(), nullable=True))
    op.add_column("lesson", sa.Column("rag_summary_stored_hash", sa.String(), nullable=True))
    op.add_column("lesson", sa.Column("rag_edited_current_hash", sa.String(), nullable=True))
    op.add_column("lesson", sa.Column("rag_edited_stored_hash", sa.String(), nullable=True))

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS lesson_chunk (
            id BIGSERIAL PRIMARY KEY,
            variant VARCHAR NOT NULL CHECK (variant IN ('edited', 'summary')),
            previous_paragraph TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            embedding vector NOT NULL,
            lesson_id INTEGER NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content_tsv TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('simple', coalesce(content, ''))
            ) STORED,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            UNIQUE (lesson_id, variant, chunk_index)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lesson_chunk_lesson_variant
        ON lesson_chunk (lesson_id, variant)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lesson_chunk_variant_chunk
        ON lesson_chunk (variant, chunk_index)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_lesson_chunk_content_tsv
        ON lesson_chunk USING GIN (content_tsv)
    """)

def downgrade() -> None:
    op.drop_table("lesson_chunk")
    op.drop_column("lesson", "rag_edited_stored_hash")
    op.drop_column("lesson", "rag_edited_current_hash")
    op.drop_column("lesson", "rag_summary_stored_hash")
    op.drop_column("lesson", "rag_summary_current_hash")
