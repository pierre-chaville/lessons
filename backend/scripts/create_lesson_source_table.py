"""Migration script to create lesson_source table and migrate existing
sources from the edited_transcript JSON field into the new table."""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlmodel import SQLModel, Session, select
from database import DATABASE_URL
from models import LessonSource, Lesson
from services.edited_transcript import normalize_edited_transcript_payload

engine = create_engine(DATABASE_URL)


def create_lesson_source_table():
    """Create the lesson_source table (if it doesn't exist yet)."""
    print("Creating lesson_source table...")
    SQLModel.metadata.create_all(engine, tables=[LessonSource.__table__])
    print("Successfully created lesson_source table")


def migrate_existing_sources():
    """Migrate sources embedded in edited_transcript JSON into the lesson_source table."""
    print("Migrating existing sources from edited_transcript JSON...")

    with Session(engine) as session:
        # Fetch lessons that have an edited_transcript
        lessons = session.exec(
            select(Lesson).where(Lesson.edited_transcript.isnot(None))
        ).all()

        total_migrated = 0
        for lesson in lessons:
            edited_parts = lesson.edited_transcript
            if not edited_parts:
                continue

            # If it's still a raw string (shouldn't be with JSON column), parse it
            if isinstance(edited_parts, str):
                edited_parts = json.loads(edited_parts)

            # Check if sources already exist for this lesson
            existing = session.exec(
                select(LessonSource).where(LessonSource.lesson_id == lesson.id)
            ).first()
            if existing:
                print(f"  Lesson {lesson.id}: already has sources in table, skipping.")
                continue

            payload = normalize_edited_transcript_payload(edited_parts)
            sources_rows = payload.get("sources", []) or []

            lesson_source_count = 0
            for para_idx, para_sources in enumerate(sources_rows):
                sources = para_sources if isinstance(para_sources, list) else []
                for src in sources:
                    ls = LessonSource(
                        lesson_id=lesson.id,
                        paragraph_index=para_idx,
                        type=src.get("type"),
                        work=src.get("work"),
                        ref=src.get("ref"),
                        standard_slug=src.get("standard_slug"),
                        original_text=src.get("original_text"),
                        translation_text=src.get("translation_text"),
                        cited_excerpt=src.get("cited_excerpt"),
                        confidence=src.get("confidence"),
                        slug_retrieved=src.get("slug_retrieved"),
                        verification_status=src.get("verification_status"),
                        verification_confidence=src.get("verification_confidence"),
                        verification_explanation=src.get("verification_explanation"),
                        matched_text=src.get("matched_text"),
                    )
                    session.add(ls)
                    lesson_source_count += 1

            if lesson_source_count > 0:
                print(f"  Lesson {lesson.id}: migrated {lesson_source_count} sources")
                total_migrated += lesson_source_count

        session.commit()
        print(f"Migration complete: {total_migrated} sources migrated across {len(lessons)} lessons")


if __name__ == "__main__":
    create_lesson_source_table()
    migrate_existing_sources()
