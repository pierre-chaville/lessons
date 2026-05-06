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
    LessonEditorResponse,
)
from schemas.source import LessonSourceResponse
from schemas.course import CourseResponse
from schemas.theme import ThemeResponse
from storage import rename_audio_object, s3_enabled
from hashid_utils import encode_id
from models.versioning import ContentType, VersionSource
from services.audit import log_event
from services.versioning import seal_all_current_versions, update_content


def _build_course_resp(course) -> CourseResponse | None:
    """Convert a Course DB model to CourseResponse with hashid."""
    if course is None:
        return None
    return CourseResponse(
        id=course.id,
        hashid=encode_id(course.id),
        name=course.name,
        description=course.description,
        parent_id=course.parent_id,
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


def _build_editor_resps(db_editors) -> list[LessonEditorResponse]:
    """Convert LessonEditor DB rows to LessonEditorResponse schemas."""
    return [LessonEditorResponse.model_validate(e) for e in db_editors]


def build_lesson_response(lesson: Lesson, session: Session) -> LessonResponse:
    """Build a full LessonResponse enriched with resolved themes, course, sources, and editors."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    db_sources = crud.get_lesson_sources(session, lesson.id)
    db_editors = crud.get_lesson_editors(session, lesson.id)
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
        status=lesson.status or "draft",
        process_status=lesson.process_status,
        theme_ids=theme_ids,
        themes=_build_theme_resps(themes),
        course=_build_course_resp(lesson.course),
        sources=_build_source_resps(db_sources),
        editors=_build_editor_resps(db_editors),
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata,
        edited_metadata=lesson.edited_metadata,
    )


def build_lesson_list_item(lesson: Lesson, session: Session) -> LessonListResponse:
    """Build a lightweight LessonListResponse enriched with resolved themes and course."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    db_editors = crud.get_lesson_editors(session, lesson.id)
    return LessonListResponse(
        id=lesson.id,
        hashid=encode_id(lesson.id),
        title=lesson.title,
        date=lesson.date,
        duration=lesson.duration,
        brief=lesson.brief,
        status=lesson.status or "draft",
        process_status=lesson.process_status,
        filename=lesson.filename,
        themes=_build_theme_resps(themes),
        course=_build_course_resp(lesson.course),
        editors=_build_editor_resps(db_editors),
    )


def create_lesson_with_audio(
    lesson_data: LessonCreate, session: Session, assigned_by: Optional[str] = None,
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

    if lesson_data.corrected_transcript is not None:
        update_content(
            session=session,
            lesson_id=lesson.id,
            content_type=ContentType.CORRECTED_TRANSCRIPT,
            new_content=lesson_data.corrected_transcript,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Initial corrected transcript",
        )
    if lesson_data.summary is not None:
        update_content(
            session=session,
            lesson_id=lesson.id,
            content_type=ContentType.SUMMARY,
            new_content=lesson_data.summary,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Initial summary",
        )

    # Rename the temporary audio object to include the lesson ID
    new_filename = (
        f"{lesson.id}_{lesson_data.filename.replace('temp_', '').split('_', 1)[-1]}"
    )
    rename_audio_object(lesson_data.filename, new_filename)

    # Store only the base name (without the ID prefix) on the lesson
    lesson.filename = new_filename.split("_", 1)[-1]
    session.add(lesson)

    if lesson_data.editor_ids:
        crud.set_lesson_editors(session, lesson.id, lesson_data.editor_ids, assigned_by=assigned_by)

    session.commit()
    session.refresh(lesson)
    log_event(
        session=session,
        actor={"sub": assigned_by, "role": "publisher"},
        entity_type="lesson",
        entity_id=str(lesson.id),
        action="lesson.created",
        payload={"title": lesson.title, "course_id": lesson.course_id},
    )
    session.commit()

    return build_lesson_response(lesson, session)


def update_lesson_data(
    lesson_id: int, lesson_data: LessonUpdate, session: Session, assigned_by: Optional[str] = None,
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
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=transcript_data,
        process_status=lesson_data.process_status,
        theme_ids=lesson_data.theme_ids,
        transcript_metadata=lesson_data.transcript_metadata,
        correction_metadata=lesson_data.correction_metadata,
        summary_metadata=lesson_data.summary_metadata,
        edited_metadata=lesson_data.edited_metadata,
    )

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    actor = {"sub": assigned_by, "role": "editor"}
    if lesson_data.title is not None:
        lesson.title = lesson_data.title
        session.add(lesson)
    if corrected_transcript_data is not None:
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.CORRECTED_TRANSCRIPT,
            new_content=corrected_transcript_data,
            actor=actor,
            source=VersionSource.HUMAN,
            change_summary="Corrected transcript updated",
        )
    if edited_transcript_data is not None:
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.EDITED_TRANSCRIPT,
            new_content=edited_transcript_data,
            actor=actor,
            source=VersionSource.HUMAN,
            change_summary="Edited transcript updated",
        )
    if lesson_data.brief is not None:
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.BRIEF,
            new_content=lesson_data.brief,
            actor=actor,
            source=VersionSource.HUMAN,
            change_summary="Brief updated",
        )
    if lesson_data.summary is not None:
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.SUMMARY,
            new_content=lesson_data.summary,
            actor=actor,
            source=VersionSource.HUMAN,
            change_summary="Summary updated",
        )

    if lesson_data.editor_ids is not None:
        crud.set_lesson_editors(session, lesson.id, lesson_data.editor_ids, assigned_by=assigned_by)
    # Persist all versioned-content updates and optional editor changes.
    session.commit()
    session.refresh(lesson)

    return build_lesson_response(lesson, session)


def change_status(
    session: Session,
    lesson: Lesson,
    new_status: str,
    actor: dict,
    reason: str | None = None,
) -> Lesson:
    old_status = lesson.status or "draft"
    lesson.status = new_status
    session.add(lesson)
    seal_all_current_versions(
        session=session,
        lesson_id=lesson.id,
        reason="status_changed",
        actor=actor,
    )
    log_event(
        session=session,
        actor=actor,
        entity_type="lesson",
        entity_id=str(lesson.id),
        action="lesson.status_changed",
        payload={"from": old_status, "to": new_status, "reason": reason},
    )
    session.commit()
    session.refresh(lesson)
    return lesson
