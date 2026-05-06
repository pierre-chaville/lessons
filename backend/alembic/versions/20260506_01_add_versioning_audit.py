"""add content_version and audit_log tables

Revision ID: 20260506_01
Revises:
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260506_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_edited_at", sa.DateTime(), nullable=True),
        sa.Column("edit_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_sealed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sealed_at", sa.DateTime(), nullable=True),
        sa.Column("sealed_reason", sa.String(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("change_summary", sa.String(), nullable=True),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("restored_from_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["content_version.id"]),
        sa.ForeignKeyConstraint(["restored_from_id"], ["content_version.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "content_type", "version_number", name="uq_content_version_number"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_audit_entity_timeline", "audit_log", ["entity_type", "entity_id", "occurred_at"])
    op.execute("""
        CREATE UNIQUE INDEX ix_one_current_per_type
        ON content_version (lesson_id, content_type)
        WHERE is_current = true
    """)

    op.execute("""
        INSERT INTO content_version (
            id, lesson_id, content_type, content, version_number, version_source,
            created_at, last_edited_at, edit_count, is_sealed, sealed_at, sealed_reason,
            created_by_id, change_summary, parent_version_id, restored_from_id, is_current
        )
        SELECT
            gen_random_uuid(), l.id, 'title', to_jsonb(l.title), 1, 'pipeline',
            COALESCE(l.date, now()), NULL, 1, true, now(), 'backfill',
            NULL, 'Initial version (backfilled at migration)', NULL, NULL, true
        FROM lesson l
        WHERE l.title IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("content_version")
