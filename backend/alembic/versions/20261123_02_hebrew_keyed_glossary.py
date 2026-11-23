"""hebrew-keyed glossary; keep transliteration glossary as legacy

The transliteration glossary (standard, variations, exact_case) is renamed to
glossary_legacy_entry and kept read-only. A new glossary_entry table keyed by
hebrew_norm is created empty. Mirrors database._migrate_legacy_glossary_table.

Revision ID: 20261123_02
Revises: 20261123_01
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261123_02"
down_revision = "20261123_01"
branch_labels = None
depends_on = None


def _create_glossary_entry_table() -> None:
    op.create_table(
        "glossary_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hebrew", sa.String(), nullable=False),
        sa.Column("hebrew_norm", sa.String(), nullable=False),
        sa.Column("hebrew_cons", sa.String(), nullable=False),
        sa.Column("translit", sa.String(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("case_flag", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("context_lesson", sa.String(), nullable=True),
        sa.Column("context_paragraph", sa.Text(), nullable=True),
        sa.Column("translation", sa.String(), nullable=True),
        sa.Column("sefaria_title", sa.String(), nullable=True),
        sa.Column("sefaria_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_glossary_entry_hebrew_norm", "glossary_entry", ["hebrew_norm"], unique=True)
    op.create_index("ix_glossary_entry_hebrew_cons", "glossary_entry", ["hebrew_cons"])
    op.create_index("ix_glossary_entry_translit", "glossary_entry", ["translit"])
    op.create_index("ix_glossary_entry_type", "glossary_entry", ["type"])
    op.create_index("ix_glossary_entry_status", "glossary_entry", ["status"])


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "glossary_entry" in tables:
        columns = {col["name"] for col in inspector.get_columns("glossary_entry")}
        if "standard" not in columns:
            return  # Already migrated (e.g. by the app's startup migration).
        if "glossary_legacy_entry" in tables:
            op.drop_table("glossary_legacy_entry")
        op.rename_table("glossary_entry", "glossary_legacy_entry")
        op.execute("ALTER INDEX IF EXISTS glossary_entry_pkey RENAME TO glossary_legacy_entry_pkey")
        op.execute("ALTER INDEX IF EXISTS ix_glossary_entry_standard RENAME TO ix_glossary_legacy_entry_standard")
        op.execute("ALTER SEQUENCE IF EXISTS glossary_entry_id_seq RENAME TO glossary_legacy_entry_id_seq")
    _create_glossary_entry_table()


def downgrade() -> None:
    op.drop_table("glossary_entry")
    op.rename_table("glossary_legacy_entry", "glossary_entry")
    op.execute("ALTER INDEX IF EXISTS glossary_legacy_entry_pkey RENAME TO glossary_entry_pkey")
    op.execute("ALTER INDEX IF EXISTS ix_glossary_legacy_entry_standard RENAME TO ix_glossary_entry_standard")
    op.execute("ALTER SEQUENCE IF EXISTS glossary_legacy_entry_id_seq RENAME TO glossary_entry_id_seq")
