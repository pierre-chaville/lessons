"""Unit tests for independent lesson list step flags."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from models.lesson import Lesson
from models.lesson_source import LessonSource
from services.lessons import build_lesson_list_item


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _lesson(session: Session, **kwargs) -> Lesson:
    lesson = Lesson(
        title="Lesson",
        filename="file.mp3",
        date=datetime.utcnow(),
        transcript=[],
        status="draft",
        **kwargs,
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def test_step_flags_are_computed_independently_from_data() -> None:
    with _session() as session:
        lesson = _lesson(
            session,
            edited_transcript={
                "markdown": "Edited",
                "sources": [[]],
                "alignment": [],
                "transcript_hash": None,
                "markdown_hash": None,
                "aligned_at": None,
            },
            summary="Final summary",
            process_status="edition",
            step_statuses={
                "transcription": "completed",
                "edited": "completed",
                "sources": "completed",
                "summary": "to_review",
                "brief": "non_started",
            },
        )
        source = LessonSource(
            lesson_id=lesson.id,
            paragraph_index=0,
            work="Pirkei Avot",
            ref="1:1",
        )
        session.add(source)
        session.commit()

        row = build_lesson_list_item(lesson, session)

        assert row.edition_done is True
        assert row.sources_done is True
        assert row.summary_done is True
        assert row.hebrew_date is not None
        assert row.hebrew_date.isdigit()


def test_step_flags_fallback_to_process_status_independently() -> None:
    with _session() as session:
        lesson = _lesson(
            session,
            edited_transcript=None,
            summary=None,
            brief=None,
            process_status="sources_extraction",
            step_statuses={
                "transcription": "non_started",
                "edited": "to_review",
                "sources": "to_review",
                "summary": "non_started",
                "brief": "non_started",
            },
        )

        row = build_lesson_list_item(lesson, session)

        assert row.edition_done is True
        assert row.sources_done is True
        assert row.summary_done is False
        assert row.hebrew_date is not None
        assert row.hebrew_date.isdigit()
