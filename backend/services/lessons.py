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
from storage import rename_audio_object, s3_enabled


def build_lesson_response(lesson: Lesson, session: Session) -> LessonResponse:
    """Build a full LessonResponse enriched with resolved themes and course."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    return LessonResponse(
        id=lesson.id,
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
        theme_ids=theme_ids,
        themes=themes,
        course=lesson.course,
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
        title=lesson.title,
        date=lesson.date,
        duration=lesson.duration,
        brief=lesson.brief,
        filename=lesson.filename,
        themes=themes,
        course=lesson.course,
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
        theme_ids=lesson_data.theme_ids,
        transcript_metadata=lesson_data.transcript_metadata,
        correction_metadata=lesson_data.correction_metadata,
        summary_metadata=lesson_data.summary_metadata,
        edited_metadata=lesson_data.edited_metadata,
    )

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    return build_lesson_response(lesson, session)
