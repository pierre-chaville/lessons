"""Business logic for lesson management."""

from sqlmodel import Session
from fastapi import HTTPException
from typing import List, Optional, Literal
from datetime import datetime
import csv
import io
import re
from convertdate import hebrew

import crud
from models import Lesson
from schemas.lesson import (
    LessonCreate,
    LessonUpdate,
    LessonListResponse,
    LessonResponse,
    LessonEditorResponse,
    VALID_STATUSES,
    USER_MUTABLE_WORKFLOW_STEP_STATUSES,
    WORKER_MUTABLE_WORKFLOW_STEP_STATUSES,
    WORKFLOW_STEP_KEYS,
    WORKFLOW_STEP_STATUSES,
)
from schemas.source import LessonSourceResponse
from schemas.course import CourseResponse
from schemas.theme import ThemeResponse
from storage import rename_audio_object, s3_enabled
from config import load_config
from hashid_utils import encode_id
from models.versioning import ContentType, VersionSource
from services.audit import log_event
from services.edited_transcript import (
    build_edited_transcript_payload,
    edited_transcript_markdown,
    normalize_edited_transcript_payload,
)
from services.summary_alignment import build_summary_alignment_metadata
from services.glossary_apply import (
    apply_glossary_to_segments,
    apply_glossary_to_text,
    load_glossary_rules,
)
from services.versioning import seal_all_current_versions, update_content
from routers.users import _get_cached_users


WORKFLOW_DONE_STATUSES = {"to_review", "completed", "validated"}


def default_step_statuses() -> dict[str, str]:
    return {step: "non_started" for step in WORKFLOW_STEP_KEYS}


def normalize_step_statuses(raw: Optional[dict]) -> dict[str, str]:
    statuses = default_step_statuses()
    if not isinstance(raw, dict):
        return statuses

    legacy_edited_statuses: list[str] = []
    legacy_sources_statuses: list[str] = []

    for key, value in raw.items():
        if not isinstance(value, str) or value not in WORKFLOW_STEP_STATUSES:
            continue
        if key in WORKFLOW_STEP_KEYS:
            statuses[key] = value
            continue
        if key in {"correction", "edition"}:
            legacy_edited_statuses.append(value)
            continue
        if key == "extraction":
            legacy_sources_statuses.append(value)

    if statuses["edited"] == "non_started" and legacy_edited_statuses:
        statuses["edited"] = legacy_edited_statuses[-1]
    if statuses["sources"] == "non_started" and legacy_sources_statuses:
        statuses["sources"] = legacy_sources_statuses[-1]

    return statuses


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


def _user_display_name(user) -> str | None:
    """Build a readable display name from a Clerk user."""
    if not user:
        return None
    name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    return name or user.username or user.email or None


def _get_user_name_by_id() -> dict[str, str]:
    """Return a map of Clerk user id -> display name."""
    try:
        users = _get_cached_users()
    except Exception:
        return {}

    by_id: dict[str, str] = {}
    for user in users:
        display_name = _user_display_name(user)
        if display_name:
            by_id[user.id] = display_name
    return by_id


def _build_editor_resps(db_editors) -> list[LessonEditorResponse]:
    """Convert LessonEditor DB rows to LessonEditorResponse schemas."""
    user_name_by_id = _get_user_name_by_id()
    return [
        LessonEditorResponse.model_validate({
            "user_id": editor.user_id,
            "user_name": user_name_by_id.get(editor.user_id),
            "assigned_at": editor.assigned_at,
            "assigned_by": editor.assigned_by,
        })
        for editor in db_editors
    ]


def _build_hebrew_date(date_value: datetime | None) -> str | None:
    """Convert a Gregorian datetime to a Hebrew year string."""
    if date_value is None:
        return None
    year, _month, _day = hebrew.from_gregorian(
        date_value.year,
        date_value.month,
        date_value.day,
    )
    return str(year)


def build_lesson_response(lesson: Lesson, session: Session) -> LessonResponse:
    """Build a full LessonResponse enriched with resolved themes, course, sources, and editors."""
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
    db_sources = crud.get_lesson_sources(session, lesson.id)
    db_editors = crud.get_lesson_editors(session, lesson.id)
    edited_payload = None
    if lesson.edited_transcript:
        try:
            edited_payload = normalize_edited_transcript_payload(lesson.edited_transcript)
        except ValueError:
            edited_payload = None
    return LessonResponse(
        id=lesson.id,
        hashid=encode_id(lesson.id),
        title=lesson.title,
        filename=lesson.filename,
        course_id=lesson.course_id,
        date=lesson.date,
        hebrew_date=_build_hebrew_date(lesson.date),
        duration=lesson.duration,
        transcript=lesson.transcript,
        corrected_transcript=lesson.corrected_transcript,
        edited_transcript=edited_payload,
        brief=lesson.brief,
        summary=lesson.summary,
        status=lesson.status or "draft",
        process_status=lesson.process_status,
        step_statuses=normalize_step_statuses(lesson.step_statuses),
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
    db_sources = crud.get_lesson_sources(session, lesson.id)

    statuses = normalize_step_statuses(lesson.step_statuses)
    edition_done = statuses["edited"] in WORKFLOW_DONE_STATUSES
    sources_done = statuses["sources"] in WORKFLOW_DONE_STATUSES
    summary_done = statuses["summary"] in WORKFLOW_DONE_STATUSES

    return LessonListResponse(
        id=lesson.id,
        hashid=encode_id(lesson.id),
        title=lesson.title,
        date=lesson.date,
        hebrew_date=_build_hebrew_date(lesson.date),
        duration=lesson.duration,
        brief=lesson.brief,
        status=lesson.status or "draft",
        process_status=lesson.process_status,
        step_statuses=statuses,
        edition_done=edition_done,
        sources_done=sources_done,
        summary_done=summary_done,
        filename=lesson.filename,
        themes=_build_theme_resps(themes),
        course=_build_course_resp(lesson.course),
        editors=_build_editor_resps(db_editors),
    )


def export_lessons_csv(session: Session) -> str:
    """Export lessons to CSV for admin bulk updates."""
    lessons = crud.get_all_lessons(session)
    course_by_id = {c.id: c for c in crud.get_all_courses(session)}
    theme_by_id = {t.id: t for t in crud.get_all_themes(session)}

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "title",
            "filename",
            "status",
            "date",
            "course_id",
            "course_name",
            "theme_ids",
            "theme_names",
            "editor_ids",
        ],
    )
    writer.writeheader()

    for lesson in lessons:
        theme_ids = lesson.get_themes()
        theme_names = [theme_by_id[t_id].name for t_id in theme_ids if t_id in theme_by_id]
        editors = crud.get_lesson_editors(session, lesson.id)
        course = course_by_id.get(lesson.course_id) if lesson.course_id else None

        writer.writerow(
            {
                "id": lesson.id,
                "title": lesson.title,
                "filename": lesson.filename,
                "status": lesson.status or "draft",
                "date": lesson.date.date().isoformat(),
                "course_id": course.id if course else "",
                "course_name": course.name if course else "",
                "theme_ids": "|".join(str(t_id) for t_id in theme_ids),
                "theme_names": "|".join(theme_names),
                "editor_ids": "|".join(e.user_id for e in editors),
            }
        )
    return output.getvalue()


def _split_csv_list(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[|,]", raw) if part.strip()]


def _parse_lesson_date(raw: str) -> datetime:
    value = raw.strip()
    if not value:
        raise ValueError("Date value is empty")
    # Support both date-only and datetime ISO values from spreadsheet edits.
    # We persist dates as date-only (00:00:00) to avoid timezone drift in UI.
    if "T" not in value and " " not in value:
        date_value = datetime.fromisoformat(value).date()
        return datetime.combine(date_value, datetime.min.time())

    datetime_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.combine(datetime_value.date(), datetime.min.time())


def import_lessons_csv(
    session: Session,
    csv_bytes: bytes,
    assigned_by: Optional[str] = None,
) -> dict:
    """Import lesson updates from CSV. Only changed fields are persisted."""
    try:
        decoded = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames or "id" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must contain an 'id' column")

    courses = crud.get_all_courses(session)
    course_by_id = {c.id: c for c in courses}
    course_id_by_name = {c.name.strip().lower(): c.id for c in courses}
    themes = crud.get_all_themes(session)
    theme_by_id = {t.id: t for t in themes}
    theme_id_by_name = {t.name.strip().lower(): t.id for t in themes}

    updated_ids: list[int] = []
    errors: list[str] = []
    total_rows = 0

    for line_no, row in enumerate(reader, start=2):
        total_rows += 1
        lesson_id_raw = str(row.get("id", "")).strip()
        if not lesson_id_raw:
            errors.append(f"Line {line_no}: missing lesson id")
            continue
        if not lesson_id_raw.isdigit():
            errors.append(f"Line {line_no}: invalid lesson id '{lesson_id_raw}'")
            continue

        lesson_id = int(lesson_id_raw)
        lesson = crud.get_lesson(session, lesson_id)
        if not lesson:
            errors.append(f"Line {line_no}: lesson {lesson_id} not found")
            continue

        changed = False

        try:
            status_raw = str(row.get("status", "")).strip()
            if status_raw and status_raw != (lesson.status or "draft"):
                if status_raw not in VALID_STATUSES:
                    raise ValueError(f"invalid status '{status_raw}'")
                lesson.status = status_raw
                changed = True

            date_raw = str(row.get("date", "")).strip()
            if date_raw:
                parsed_date = _parse_lesson_date(date_raw)
                if lesson.date != parsed_date:
                    lesson.date = parsed_date
                    changed = True

            if "course_id" in row or "course_name" in row:
                course_id_raw = str(row.get("course_id", "")).strip()
                course_name_raw = str(row.get("course_name", "")).strip()
                if course_id_raw:
                    if not course_id_raw.isdigit():
                        raise ValueError(f"invalid course_id '{course_id_raw}'")
                    next_course_id = int(course_id_raw)
                    if next_course_id not in course_by_id:
                        raise ValueError(f"course_id '{next_course_id}' does not exist")
                elif course_name_raw:
                    next_course_id = course_id_by_name.get(course_name_raw.lower())
                    if next_course_id is None:
                        raise ValueError(f"course_name '{course_name_raw}' does not exist")
                else:
                    next_course_id = None

                if lesson.course_id != next_course_id:
                    lesson.course_id = next_course_id
                    changed = True

            if "theme_ids" in row or "theme_names" in row:
                theme_ids_raw = str(row.get("theme_ids", "")).strip()
                theme_names_raw = str(row.get("theme_names", "")).strip()

                if theme_ids_raw:
                    next_theme_ids = [int(v) for v in _split_csv_list(theme_ids_raw)]
                    unknown_ids = [t_id for t_id in next_theme_ids if t_id not in theme_by_id]
                    if unknown_ids:
                        raise ValueError(f"unknown theme_ids: {unknown_ids}")
                elif theme_names_raw:
                    next_theme_ids = []
                    for name in _split_csv_list(theme_names_raw):
                        theme_id = theme_id_by_name.get(name.lower())
                        if theme_id is None:
                            raise ValueError(f"theme '{name}' does not exist")
                        next_theme_ids.append(theme_id)
                else:
                    next_theme_ids = []

                current_theme_ids = lesson.get_themes()
                if sorted(current_theme_ids) != sorted(next_theme_ids):
                    lesson.set_themes(next_theme_ids)
                    changed = True

            if "editor_ids" in row:
                next_editor_ids = _split_csv_list(str(row.get("editor_ids", "")).strip())
                current_editor_ids = [e.user_id for e in crud.get_lesson_editors(session, lesson.id)]
                if sorted(current_editor_ids) != sorted(next_editor_ids):
                    crud.set_lesson_editors(
                        session,
                        lesson.id,
                        next_editor_ids,
                        assigned_by=assigned_by,
                    )
                    changed = True

            if changed:
                session.add(lesson)
                updated_ids.append(lesson.id)
        except ValueError as exc:
            errors.append(f"Line {line_no} (lesson {lesson_id}): {exc}")

    session.commit()
    return {
        "updated_count": len(updated_ids),
        "skipped_count": max(0, total_rows - len(updated_ids) - len(errors)),
        "error_count": len(errors),
        "updated_ids": updated_ids,
        "errors": errors,
    }


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
    if lesson_data.step_statuses is not None:
        raise HTTPException(
            status_code=400,
            detail="Use /lessons/{lesson_hashid}/steps/{step}/status to update workflow step statuses",
        )

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
        edited_transcript_data = (
            lesson_data.edited_transcript.model_dump(mode="json")
            if hasattr(lesson_data.edited_transcript, "model_dump")
            else lesson_data.edited_transcript
        )

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


def set_lesson_step_status(
    session: Session,
    lesson_id: int,
    step: str,
    status: str,
    actor: Optional[dict] = None,
    updated_by: Literal["user", "worker"] = "user",
) -> Lesson:
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if step not in WORKFLOW_STEP_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid workflow step: {step}")
    if status not in WORKFLOW_STEP_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid step status: {status}")

    # No-op updates are always allowed, even for statuses not user-mutable.
    statuses = normalize_step_statuses(lesson.step_statuses)
    previous_status = statuses.get(step, "non_started")
    if previous_status == status:
        return lesson

    allowed_statuses = (
        USER_MUTABLE_WORKFLOW_STEP_STATUSES
        if updated_by == "user"
        else WORKER_MUTABLE_WORKFLOW_STEP_STATUSES
    )
    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Status '{status}' cannot be set by {updated_by}. "
                f"Allowed: {', '.join(sorted(allowed_statuses))}"
            ),
        )

    statuses[step] = status
    lesson.step_statuses = statuses
    session.add(lesson)
    if actor:
        log_event(
            session=session,
            actor=actor,
            entity_type="lesson",
            entity_id=str(lesson.id),
            action="lesson.step_status_changed",
            payload={
                "step": step,
                "from": previous_status,
                "to": status,
                "updated_by": updated_by,
            },
        )
    session.commit()
    session.refresh(lesson)
    return lesson


def realign_edited_markdown(
    lesson_id: int, session: Session, actor: Optional[dict] = None
) -> LessonResponse:
    """Recompute edited transcript alignment from current markdown + transcript."""
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.edited_transcript:
        raise HTTPException(status_code=404, detail="No edited transcript available")

    payload = normalize_edited_transcript_payload(lesson.edited_transcript)
    markdown = str(payload.get("markdown", "")).strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="Edited transcript markdown is empty")

    transcript = lesson.corrected_transcript or lesson.transcript
    if not transcript:
        raise HTTPException(status_code=400, detail="No transcript available for alignment")
    glossary_rules = load_glossary_rules(session)
    alignment_config = load_config().get("alignment", {})
    try:
        edited_min_alignment_score = float(
            alignment_config.get("edited_min_score", 0.2)
        )
    except (TypeError, ValueError):
        edited_min_alignment_score = 0.2
    edited_min_alignment_score = max(0.0, min(1.0, edited_min_alignment_score))

    refreshed_payload = build_edited_transcript_payload(
        markdown=apply_glossary_to_text(markdown, glossary_rules),
        transcript=apply_glossary_to_segments(transcript, glossary_rules),
        sources=payload.get("sources"),
        min_alignment_score=edited_min_alignment_score,
    )
    update_content(
        session=session,
        lesson_id=lesson_id,
        content_type=ContentType.EDITED_TRANSCRIPT,
        new_content=refreshed_payload,
        actor=actor,
        source=VersionSource.HUMAN if actor else VersionSource.PIPELINE,
        change_summary="Edited transcript alignment refreshed",
    )
    session.commit()
    session.refresh(lesson)
    return build_lesson_response(lesson, session)


def realign_summary_alignment(
    lesson_id: int, session: Session
) -> LessonResponse:
    """Recompute summary alignment against current edited markdown."""
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.summary:
        raise HTTPException(status_code=404, detail="No summary available")
    if not lesson.edited_transcript:
        raise HTTPException(status_code=404, detail="No edited transcript available")

    edited_markdown = edited_transcript_markdown(lesson.edited_transcript).strip()
    if not edited_markdown:
        raise HTTPException(status_code=400, detail="Edited transcript markdown is empty")
    glossary_rules = load_glossary_rules(session)
    alignment_config = load_config().get("alignment", {})
    try:
        summary_min_alignment_score = float(
            alignment_config.get("summary_min_score", 0.2)
        )
    except (TypeError, ValueError):
        summary_min_alignment_score = 0.2
    summary_min_alignment_score = max(0.0, min(1.0, summary_min_alignment_score))

    current_metadata = lesson.summary_metadata or {}
    refreshed = build_summary_alignment_metadata(
        summary_markdown=apply_glossary_to_text(str(lesson.summary), glossary_rules),
        edited_markdown=apply_glossary_to_text(edited_markdown, glossary_rules),
        min_alignment_score=summary_min_alignment_score,
    )
    lesson.summary_metadata = {**current_metadata, **refreshed}
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return build_lesson_response(lesson, session)
