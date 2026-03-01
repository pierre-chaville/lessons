"""Business logic for lesson management."""

from sqlmodel import Session
from fastapi import HTTPException
from typing import List, Optional

import crud
from models import Lesson
from schemas.lesson import (
    LessonCreate,
    LessonUpdate,
    LessonListResponse,
    LessonResponse,
)
from schemas.source import LessonSourceResponse
from schemas.course import CourseResponse
from schemas.theme import ThemeResponse
from storage import rename_audio_object, s3_enabled
from hashid_utils import encode_id


def _build_course_resp(course) -> CourseResponse | None:
    """Convert a Course DB model to CourseResponse with hashid."""
    if course is None:
        return None
    return CourseResponse(
        id=course.id,
        hashid=encode_id(course.id),
        name=course.name,
        description=course.description,
    )


def _build_theme_resps(themes) -> list[ThemeResponse]:
    """Convert a list of Theme DB models to ThemeResponse with hashids."""
    return [
        ThemeResponse(id=t.id, hashid=encode_id(t.id), name=t.name)
        for t in themes
    ]


def _build_source_resps(db_sources) -> list[LessonSourceResponse]:
    """Convert LessonSource DB rows to LessonSourceResponse schemas."""
    return [LessonSourceResponse.model_validate(s) for s in db_sources]


def build_lesson_response(lesson: Lesson, session: Session) -> LessonResponse:
    """Build a full LessonResponse enriched with resolved themes, course, and sources."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    db_sources = crud.get_lesson_sources(session, lesson.id)
    return LessonResponse(
        id=lesson.id,
        hashid=encode_id(lesson.id),
        title=lesson.title,
        filename=lesson.filename,
        course_id=lesson.course_id,
        date=lesson.date,
        duration=lesson.duration,
        transcript=lesson.transcript,
        corrected_transcript=lesson.corrected_transcript,
        edited_transcript=lesson.edited_transcript,
        brief=lesson.brief,
        summary=lesson.summary,
        process_status=lesson.process_status,
        theme_ids=theme_ids,
        themes=_build_theme_resps(themes),
        course=_build_course_resp(lesson.course),
        sources=_build_source_resps(db_sources),
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata,
        edited_metadata=lesson.edited_metadata,
    )


def build_lesson_list_item(lesson: Lesson, session: Session) -> LessonListResponse:
    """Build a lightweight LessonListResponse enriched with resolved themes and course."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    return LessonListResponse(
        id=lesson.id,
        hashid=encode_id(lesson.id),
        title=lesson.title,
        date=lesson.date,
        duration=lesson.duration,
        brief=lesson.brief,
        process_status=lesson.process_status,
        filename=lesson.filename,
        themes=_build_theme_resps(themes),
        course=_build_course_resp(lesson.course),
    )


def create_lesson_with_audio(
    lesson_data: LessonCreate, session: Session
) -> LessonResponse:
    """Validate references, persist lesson, rename audio object in S3, return enriched response."""
    if lesson_data.course_id:
        if not crud.get_course(session, lesson_data.course_id):
            raise HTTPException(status_code=404, detail="Course not found")

    if lesson_data.theme_ids:
        themes = crud.get_themes_by_ids(session, lesson_data.theme_ids)
        if len(themes) != len(lesson_data.theme_ids):
            raise HTTPException(status_code=404, detail="One or more themes not found")

    if not s3_enabled():
        raise HTTPException(status_code=500, detail="S3 is not configured")

    lesson = crud.create_lesson(
        session,
        title=lesson_data.title,
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=lesson_data.transcript,
        corrected_transcript=lesson_data.corrected_transcript,
        summary=lesson_data.summary,
        theme_ids=lesson_data.theme_ids,
    )

    # Rename the temporary audio object to include the lesson ID
    new_filename = (
        f"{lesson.id}_{lesson_data.filename.replace('temp_', '').split('_', 1)[-1]}"
    )
    rename_audio_object(lesson_data.filename, new_filename)

    # Store only the base name (without the ID prefix) on the lesson
    lesson.filename = new_filename.split("_", 1)[-1]
    session.add(lesson)
    session.commit()
    session.refresh(lesson)

    return build_lesson_response(lesson, session)


def update_lesson_data(
    lesson_id: int, lesson_data: LessonUpdate, session: Session
) -> LessonResponse:
    """Validate references, convert typed objects to dicts, persist update, return enriched response."""
    if lesson_data.course_id:
        if not crud.get_course(session, lesson_data.course_id):
            raise HTTPException(status_code=404, detail="Course not found")

    if lesson_data.theme_ids is not None:
        themes = crud.get_themes_by_ids(session, lesson_data.theme_ids)
        if len(themes) != len(lesson_data.theme_ids):
            raise HTTPException(status_code=404, detail="One or more themes not found")

    transcript_data = None
    if lesson_data.transcript is not None:
        transcript_data = [
            seg.model_dump() if hasattr(seg, "model_dump") else seg
            for seg in lesson_data.transcript
        ]

    corrected_transcript_data = None
    if lesson_data.corrected_transcript is not None:
        corrected_transcript_data = [
            seg.model_dump() if hasattr(seg, "model_dump") else seg
            for seg in lesson_data.corrected_transcript
        ]

    edited_transcript_data = None
    if lesson_data.edited_transcript is not None:
        edited_transcript_data = [
            part.model_dump() if hasattr(part, "model_dump") else part
            for part in lesson_data.edited_transcript
        ]

    lesson = crud.update_lesson(
        session,
        lesson_id,
        title=lesson_data.title,
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=transcript_data,
        corrected_transcript=corrected_transcript_data,
        edited_transcript=edited_transcript_data,
        brief=lesson_data.brief,
        summary=lesson_data.summary,
        process_status=lesson_data.process_status,
        theme_ids=lesson_data.theme_ids,
        transcript_metadata=lesson_data.transcript_metadata,
        correction_metadata=lesson_data.correction_metadata,
        summary_metadata=lesson_data.summary_metadata,
        edited_metadata=lesson_data.edited_metadata,
    )

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    return build_lesson_response(lesson, session)
