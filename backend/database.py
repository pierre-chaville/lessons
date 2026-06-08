import os
import logging
import threading
from datetime import datetime

from convertdate import hebrew
from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

load_dotenv(override=True)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATBASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (or DATBASE_URL). Check your .env.")

# Create engine
engine = create_engine(DATABASE_URL, echo=False)
_migration_lock = threading.Lock()
_migrations_completed = False


def _hebrew_year_from_datetime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    year, _month, _day = hebrew.from_gregorian(value.year, value.month, value.day)
    return str(year)


def _backfill_lesson_hebrew_years() -> int:
    updated_rows = 0
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, date
            FROM lesson
            WHERE hebrew_year IS NULL OR trim(hebrew_year) = ''
        """)).mappings().all()
        for row in rows:
            hebrew_year = _hebrew_year_from_datetime(row["date"])
            if not hebrew_year:
                continue
            result = conn.execute(
                text("UPDATE lesson SET hebrew_year = :hebrew_year WHERE id = :id"),
                {"hebrew_year": hebrew_year, "id": row["id"]},
            )
            updated_rows += max(0, result.rowcount or 0)
    return updated_rows


def _create_versioning_tables() -> None:
    """Create content version and audit tables + indexes."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS content_version (
                id UUID PRIMARY KEY,
                lesson_id INTEGER NOT NULL REFERENCES lesson(id) ON DELETE CASCADE,
                content_type VARCHAR NOT NULL,
                content JSONB NOT NULL,
                version_number INTEGER NOT NULL,
                version_source VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                last_edited_at TIMESTAMP NULL,
                edit_count INTEGER NOT NULL DEFAULT 1,
                is_sealed BOOLEAN NOT NULL DEFAULT false,
                sealed_at TIMESTAMP NULL,
                sealed_reason VARCHAR NULL,
                created_by_id VARCHAR NULL,
                change_summary VARCHAR NULL,
                parent_version_id UUID NULL REFERENCES content_version(id),
                restored_from_id UUID NULL REFERENCES content_version(id),
                is_current BOOLEAN NOT NULL DEFAULT false
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                occurred_at TIMESTAMP NOT NULL DEFAULT now(),
                actor_id VARCHAR NULL,
                actor_role VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                entity_id VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_content_version_number
            ON content_version (lesson_id, content_type, version_number)
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_one_current_per_type
            ON content_version (lesson_id, content_type)
            WHERE is_current = true
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_content_version_lesson_type
            ON content_version (lesson_id, content_type)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_content_version_created_at
            ON content_version (created_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_audit_entity_timeline
            ON audit_log (entity_type, entity_id, occurred_at DESC)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_audit_occurred_at
            ON audit_log (occurred_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_audit_actor_id
            ON audit_log (actor_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_audit_action
            ON audit_log (action)
        """))


def _create_preference_versioning_table() -> None:
    """Create global preferences version table + indexes."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS preference_version (
                id UUID PRIMARY KEY,
                content JSONB NOT NULL,
                version_number INTEGER NOT NULL,
                version_source VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                last_edited_at TIMESTAMP NULL,
                edit_count INTEGER NOT NULL DEFAULT 1,
                is_sealed BOOLEAN NOT NULL DEFAULT false,
                sealed_at TIMESTAMP NULL,
                sealed_reason VARCHAR NULL,
                created_by_id VARCHAR NULL,
                change_summary VARCHAR NULL,
                parent_version_id UUID NULL REFERENCES preference_version(id),
                restored_from_id UUID NULL REFERENCES preference_version(id),
                is_current BOOLEAN NOT NULL DEFAULT false
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_preference_version_number
            ON preference_version (version_number)
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_one_current_preference_version
            ON preference_version (is_current)
            WHERE is_current = true
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_preference_version_created_at
            ON preference_version (created_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_preference_version_created_by_id
            ON preference_version (created_by_id)
        """))


def _create_lesson_chunk_table() -> None:
    """Create RAG chunk storage with pgvector and full-text search support."""
    if engine.dialect.name != "postgresql":
        logger.warning("Skipping lesson_chunk creation: pgvector requires PostgreSQL")
        return

    with engine.begin() as conn:
        conn.execute(text("""
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
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_lesson_chunk_lesson_variant
            ON lesson_chunk (lesson_id, variant)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_lesson_chunk_variant_chunk
            ON lesson_chunk (variant, chunk_index)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_lesson_chunk_content_tsv
            ON lesson_chunk USING GIN (content_tsv)
        """))


def _ensure_content_version_lesson_fk_cascade() -> None:
    """Ensure content_version.lesson_id FK is ON DELETE CASCADE (PostgreSQL)."""
    if engine.dialect.name != "postgresql":
        return
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "content_version" not in tables or "lesson" not in tables:
        return

    lesson_fks = [
        fk for fk in inspector.get_foreign_keys("content_version")
        if fk.get("referred_table") == "lesson" and fk.get("constrained_columns") == ["lesson_id"]
    ]

    has_cascade_fk = any(
        (fk.get("options") or {}).get("ondelete", "").upper() == "CASCADE"
        for fk in lesson_fks
    )
    if has_cascade_fk:
        return

    with engine.begin() as conn:
        for fk in lesson_fks:
            fk_name = fk.get("name")
            if fk_name:
                safe_name = fk_name.replace('"', '""')
                conn.execute(text(f'ALTER TABLE content_version DROP CONSTRAINT IF EXISTS "{safe_name}"'))
        conn.execute(text("""
            ALTER TABLE content_version
            ADD CONSTRAINT content_version_lesson_id_fkey
            FOREIGN KEY (lesson_id) REFERENCES lesson(id) ON DELETE CASCADE
        """))
    logger.info("Migration: ensured ON DELETE CASCADE on content_version.lesson_id FK")


def _backfill_content_versions() -> int:
    """Backfill initial v1 rows from existing lesson cached content."""
    inserted_rows = 0
    for field_name, content_type, content_expr in (
        # Title is intentionally excluded (not tracked anymore).
        (
            "corrected_transcript",
            "corrected_transcript",
            "replace(l.corrected_transcript::text, E'\\\\u0000', '')::jsonb",
        ),
        (
            "edited_transcript",
            "edited_transcript",
            "replace(l.edited_transcript::text, E'\\\\u0000', '')::jsonb",
        ),
        # For text columns, strip escaped null bytes before JSON conversion.
        ("brief", "brief", "to_jsonb(replace(l.brief, E'\\\\u0000', ''))"),
        ("summary", "summary", "to_jsonb(replace(l.summary, E'\\\\u0000', ''))"),
    ):
        try:
            with engine.begin() as conn:
                result = conn.execute(text(f"""
                    INSERT INTO content_version (
                        id, lesson_id, content_type, content, version_number, version_source,
                        created_at, last_edited_at, edit_count, is_sealed, sealed_at, sealed_reason,
                        created_by_id, change_summary, parent_version_id, restored_from_id, is_current
                    )
                    SELECT
                        gen_random_uuid(),
                        l.id,
                        :content_type,
                        {content_expr},
                        1,
                        'pipeline',
                        COALESCE(l.date, now()),
                        NULL,
                        1,
                        true,
                        now(),
                        'backfill',
                        NULL,
                        'Initial version (backfilled at migration)',
                        NULL,
                        NULL,
                        true
                    FROM lesson l
                    WHERE l.{field_name} IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM content_version cv
                          WHERE cv.lesson_id = l.id
                            AND cv.content_type = :content_type
                      )
                """), {"content_type": content_type})
                inserted_rows += max(0, result.rowcount or 0)
        except SQLAlchemyError as exc:
            logger.warning(
                "Backfill skipped for content_type=%s due to invalid legacy data: %s",
                content_type,
                exc,
            )
    return inserted_rows


def _run_migrations():
    """Add missing columns to existing tables (lightweight auto-migration)."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "lesson" in tables:
        columns = {col["name"] for col in inspector.get_columns("lesson")}
        if "status" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE lesson ADD COLUMN status VARCHAR NOT NULL DEFAULT 'draft'"
                ))
            logger.info("Migration: added 'status' column to lesson table")
        if "step_statuses" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE lesson ADD COLUMN step_statuses JSON"))
            logger.info("Migration: added 'step_statuses' column to lesson table")
        rag_hash_columns = {
            "rag_summary_current_hash": "VARCHAR",
            "rag_summary_stored_hash": "VARCHAR",
            "rag_edited_current_hash": "VARCHAR",
            "rag_edited_stored_hash": "VARCHAR",
        }
        with engine.begin() as conn:
            if "hebrew_year" not in columns:
                conn.execute(text("ALTER TABLE lesson ADD COLUMN hebrew_year VARCHAR"))
                logger.info("Migration: added 'hebrew_year' column to lesson table")
            if "pdf_files" not in columns:
                conn.execute(text("ALTER TABLE lesson ADD COLUMN pdf_files JSON"))
                logger.info("Migration: added 'pdf_files' column to lesson table")
            if "legacy_url" not in columns:
                conn.execute(text("ALTER TABLE lesson ADD COLUMN legacy_url VARCHAR"))
                logger.info("Migration: added 'legacy_url' column to lesson table")
            for column_name, column_type in rag_hash_columns.items():
                if column_name not in columns:
                    conn.execute(text(
                        f"ALTER TABLE lesson ADD COLUMN {column_name} {column_type}"
                    ))
                    logger.info("Migration: added '%s' column to lesson table", column_name)
        try:
            backfilled_years = _backfill_lesson_hebrew_years()
            if backfilled_years > 0:
                logger.info(
                    "Migration: initialized hebrew_year for %s lesson(s)",
                    backfilled_years,
                )
        except SQLAlchemyError as exc:
            logger.warning("Hebrew year backfill failed/skipped: %s", exc)

    if "course" in tables:
        columns = {col["name"] for col in inspector.get_columns("course")}
        if "parent_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE course ADD COLUMN parent_id INTEGER REFERENCES course(id)"
                ))
            logger.info("Migration: added 'parent_id' column to course table")
        if "sort_order" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE course ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
                ))
            logger.info("Migration: added 'sort_order' column to course table")

    if "task" in tables:
        columns = {col["name"] for col in inspector.get_columns("task")}
        if "created_by_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE task ADD COLUMN created_by_id VARCHAR"
                ))
            logger.info("Migration: added 'created_by_id' column to task table")

    if "lesson" in tables:
        try:
            had_content_version = "content_version" in tables
            had_audit_log = "audit_log" in tables
            _create_versioning_tables()
            _ensure_content_version_lesson_fk_cascade()
            backfilled_count = _backfill_content_versions()
            if (not had_content_version) or (not had_audit_log) or backfilled_count > 0:
                logger.info(
                    "Migration: ensured versioning/audit schema; backfilled %s content versions",
                    backfilled_count,
                )
        except SQLAlchemyError as exc:
            logger.warning("Versioning migration step failed/skipped: %s", exc)

        try:
            _create_lesson_chunk_table()
        except SQLAlchemyError as exc:
            logger.warning("RAG chunk table migration step failed/skipped: %s", exc)

    try:
        had_preference_version = "preference_version" in tables
        _create_preference_versioning_table()
        if not had_preference_version:
            logger.info("Migration: ensured preference versioning schema")
    except SQLAlchemyError as exc:
        logger.warning("Preference versioning migration step failed/skipped: %s", exc)

    if "model_preset" in tables:
        columns = {col["name"] for col in inspector.get_columns("model_preset")}
        with engine.begin() as conn:
            if "cost_input_per_m_tokens" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE model_preset ADD COLUMN cost_input_per_m_tokens DOUBLE PRECISION NOT NULL DEFAULT 0"
                    )
                )
                logger.info(
                    "Migration: added 'cost_input_per_m_tokens' column to model_preset table"
                )
            if "cost_output_per_m_tokens" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE model_preset ADD COLUMN cost_output_per_m_tokens DOUBLE PRECISION NOT NULL DEFAULT 0"
                    )
                )
                logger.info(
                    "Migration: added 'cost_output_per_m_tokens' column to model_preset table"
                )
            if "flex_cost_ratio" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE model_preset ADD COLUMN flex_cost_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.5"
                    )
                )
                logger.info(
                    "Migration: added 'flex_cost_ratio' column to model_preset table"
                )


def create_db_and_tables():
    """Create database tables"""
    global _migrations_completed
    if _migrations_completed:
        return
    with _migration_lock:
        if _migrations_completed:
            return
        try:
            SQLModel.metadata.create_all(engine)
        except SQLAlchemyError as exc:
            # In concurrent startup scenarios (e.g. multiple init callers),
            # PostgreSQL can raise duplicate pg_type rows while creating tables.
            # If so, continue and run idempotent migrations.
            message = str(exc)
            is_concurrent_create_race = (
                "pg_type_typname_nsp_index" in message
                or ("already exists" in message and "content_version" in message)
            )
            if not is_concurrent_create_race:
                raise
            logger.warning("Concurrent table creation detected; continuing: %s", exc)
        _run_migrations()
        _migrations_completed = True


def get_session():
    """Get database session"""
    with Session(engine) as session:
        yield session

