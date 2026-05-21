"""Lessons router — /lessons endpoints including PDF and audio URL."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import List, Dict, Any, Optional, Literal

import crud
from auth import require_auth, require_roles, _extract_roles, _extract_role
from database import get_session
from schemas.lesson import (
    LessonCreate, LessonUpdate, LessonListResponse, LessonResponse,
    StatusUpdate, ALLOWED_TRANSITIONS, VALID_STATUSES,
    VersionResponse, RestoreVersionRequest, CheckpointRequest, AuditLogResponse,
    StepStatusUpdate,
    WORKFLOW_STEP_KEYS,
    LessonBulkCsvImportResponse,
)
from services import lessons as lesson_service
from services import exports as export_service
from services.audit import get_lesson_audit_log
from services.versioning import (
    ContentType,
    compute_diff,
    get_version,
    list_versions,
    restore_version,
    seal_current_version,
)
from models.versioning import ContentVersion
from hashid_utils import decode_id

router = APIRouter(prefix="/lessons", tags=["Lessons"])


def _require_lesson_access(
    lesson_id: int, claims: Dict[str, Any], session: Session
) -> None:
    """Raise 403 if the caller is an editor not assigned to this lesson.

    Publishers and admins are always allowed.
    """
    role = _extract_role(claims)
    if role in ("publisher", "admin"):
        return
    user_id = claims.get("sub", "")
    editors = crud.get_lesson_editors(session, lesson_id)
    if not any(e.user_id == user_id for e in editors):
        raise HTTPException(
            status_code=403,
            detail="You are not assigned as an editor for this lesson",
        )


def _deny_history_for_viewer(claims: Dict[str, Any]) -> None:
    role = _extract_role(claims)
    if role in ("viewer", "reader"):
        raise HTTPException(status_code=404, detail="Lesson not found")


def _build_version_response(
    version: ContentVersion,
    restored_from_version_number: Optional[int] = None,
) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        lesson_id=version.lesson_id,
        content_type=version.content_type,
        version_number=version.version_number,
        version_source=version.version_source,
        created_at=version.created_at,
        last_edited_at=version.last_edited_at,
        edit_count=version.edit_count,
        is_sealed=version.is_sealed,
        sealed_at=version.sealed_at,
        sealed_reason=version.sealed_reason,
        created_by_id=version.created_by_id,
        change_summary=version.change_summary,
        parent_version_id=version.parent_version_id,
        restored_from_id=version.restored_from_id,
        restored_from_version_number=restored_from_version_number,
        is_current=version.is_current,
        content=version.content,
    )


@router.get("", response_model=List[LessonListResponse])
def get_lessons(
    course_id: Optional[int] = Query(None, description="Filter by single course ID"),
    course_ids: Optional[str] = Query(None, description="Comma-separated course IDs"),
    session: Session = Depends(get_session),
):
    """Get all lessons (lightweight response), optionally filtered by course(s)."""
    parsed_ids = None
    if course_ids:
        parsed_ids = [int(x) for x in course_ids.split(",") if x.strip().isdigit()]
    lessons = crud.get_all_lessons(session, course_id=course_id, course_ids=parsed_ids)
    return [lesson_service.build_lesson_list_item(lesson, session) for lesson in lessons]


@router.get("/bulk/csv/export")
def export_lessons_csv(
    session: Session = Depends(get_session),
    _claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Export lessons as CSV for admin bulk edits."""
    csv_payload = lesson_service.export_lessons_csv(session)
    return Response(
        content=csv_payload.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="lessons_bulk_edit.csv"'},
    )


@router.post("/bulk/csv/import", response_model=LessonBulkCsvImportResponse)
async def import_lessons_csv(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Import lessons from admin CSV and update only changed fields."""
    filename = str(file.filename or "").lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    return lesson_service.import_lessons_csv(
        session=session,
        csv_bytes=payload,
        assigned_by=claims.get("sub"),
    )


@router.get("/{lesson_hashid}", response_model=LessonResponse)
def get_lesson(lesson_hashid: str, session: Session = Depends(get_session)):
    """Get a specific lesson by hashid with full details."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson_service.build_lesson_response(lesson, session)


@router.post("", response_model=LessonResponse, status_code=201)
def create_lesson(
    lesson_data: LessonCreate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Create a new lesson and finalize its audio object in S3."""
    return lesson_service.create_lesson_with_audio(
        lesson_data, session, assigned_by=claims.get("sub"),
    )


@router.patch("/{lesson_hashid}/status", response_model=LessonResponse)
def update_lesson_status(
    lesson_hashid: str,
    body: StatusUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_auth),
):
    """Transition lesson workflow status with role-based permission checks."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    _require_lesson_access(lesson_id, claims, session)

    current = lesson.status or "draft"
    target = body.status

    if target not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {target}")

    transitions = ALLOWED_TRANSITIONS.get(current, {})
    allowed_roles = transitions.get(target)
    if allowed_roles is None:
        raise HTTPException(
            status_code=400,
            detail=f"Transition from '{current}' to '{target}' is not allowed",
        )

    user_roles = _extract_roles(claims)
    if not any(r in allowed_roles for r in user_roles):
        raise HTTPException(
            status_code=403,
            detail="Your role cannot perform this transition",
        )

    lesson = lesson_service.change_status(
        session=session,
        lesson=lesson,
        new_status=target,
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
        reason=body.reason,
    )
    return lesson_service.build_lesson_response(lesson, session)


@router.patch("/{lesson_hashid}", response_model=LessonResponse)
def update_lesson(
    lesson_hashid: str,
    lesson_data: LessonUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Update an existing lesson. Editors must be assigned to the lesson."""
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    return lesson_service.update_lesson_data(
        lesson_id, lesson_data, session, assigned_by=claims.get("sub"),
    )


@router.patch("/{lesson_hashid}/steps/{step}/status", response_model=LessonResponse)
def update_lesson_step_status(
    lesson_hashid: str,
    step: str,
    body: StepStatusUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    if step not in WORKFLOW_STEP_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid workflow step: {step}")
    lesson = lesson_service.set_lesson_step_status(
        session=session,
        lesson_id=lesson_id,
        step=step,
        status=body.status,
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
        updated_by="user",
    )
    return lesson_service.build_lesson_response(lesson, session)


@router.post("/{lesson_hashid}/edited/realign", response_model=LessonResponse)
def realign_lesson_edited_markdown(
    lesson_hashid: str,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Refresh edited markdown alignment from the current transcript."""
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    return lesson_service.realign_edited_markdown(
        lesson_id=lesson_id,
        session=session,
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
    )


@router.post("/{lesson_hashid}/summary/realign", response_model=LessonResponse)
def realign_lesson_summary(
    lesson_hashid: str,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Refresh summary alignment from current summary + edited markdown."""
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    return lesson_service.realign_summary_alignment(
        lesson_id=lesson_id,
        session=session,
    )


@router.delete("/{lesson_hashid}", status_code=204)
def delete_lesson(
    lesson_hashid: str,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a lesson."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not crud.delete_lesson(session, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    from services.audit import log_event
    log_event(
        session=session,
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
        entity_type="lesson",
        entity_id=str(lesson_id),
        action="lesson.deleted",
        payload={"title": lesson.title},
    )
    session.commit()
    return None


@router.get("/{lesson_hashid}/versions", response_model=List[VersionResponse])
def get_lesson_versions(
    lesson_hashid: str,
    content_type: ContentType = Query(...),
    limit: int = Query(50, le=100),
    before: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["viewer", "reader", "editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _deny_history_for_viewer(claims)
    _require_lesson_access(lesson_id, claims, session)
    versions = list_versions(
        session=session,
        lesson_id=lesson_id,
        content_type=content_type,
        limit=limit,
        before=before,
    )
    restored_from_ids = [v.restored_from_id for v in versions if v.restored_from_id]
    restored_numbers: Dict[UUID, int] = {}
    if restored_from_ids:
        rows = session.exec(
            select(ContentVersion.id, ContentVersion.version_number).where(
                ContentVersion.id.in_(restored_from_ids),
            )
        ).all()
        restored_numbers = {row[0]: row[1] for row in rows}

    return [
        _build_version_response(
            v,
            restored_numbers.get(v.restored_from_id) if v.restored_from_id else None,
        )
        for v in versions
    ]


@router.get("/{lesson_hashid}/versions/{version_id}", response_model=VersionResponse)
def get_lesson_version(
    lesson_hashid: str,
    version_id: UUID,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["viewer", "reader", "editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _deny_history_for_viewer(claims)
    _require_lesson_access(lesson_id, claims, session)
    version = get_version(session, version_id)
    if version.lesson_id != lesson_id:
        raise HTTPException(status_code=404, detail="Version not found")
    restored_from_version_number = None
    if version.restored_from_id:
        restored_from = session.get(ContentVersion, version.restored_from_id)
        if restored_from:
            restored_from_version_number = restored_from.version_number
    return _build_version_response(version, restored_from_version_number)


@router.get("/{lesson_hashid}/versions/{version_a}/diff/{version_b}")
def get_lesson_versions_diff(
    lesson_hashid: str,
    version_a: UUID,
    version_b: UUID,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["viewer", "reader", "editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _deny_history_for_viewer(claims)
    _require_lesson_access(lesson_id, claims, session)
    a = get_version(session, version_a)
    b = get_version(session, version_b)
    if a.lesson_id != lesson_id or b.lesson_id != lesson_id:
        raise HTTPException(status_code=404, detail="Version not found")
    return compute_diff(a, b)


@router.post("/{lesson_hashid}/versions/{version_id}/restore", response_model=VersionResponse)
def restore_lesson_version(
    lesson_hashid: str,
    version_id: UUID,
    body: RestoreVersionRequest,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    restored = restore_version(
        session=session,
        target_version_id=version_id,
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
        reason=body.reason,
    )
    if restored.lesson_id != lesson_id:
        raise HTTPException(status_code=404, detail="Version not found")
    session.commit()
    session.refresh(restored)
    return VersionResponse.model_validate(restored)


@router.post("/{lesson_hashid}/versions/checkpoint", response_model=VersionResponse)
def checkpoint_lesson_version(
    lesson_hashid: str,
    body: CheckpointRequest,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _require_lesson_access(lesson_id, claims, session)
    version = seal_current_version(
        session=session,
        lesson_id=lesson_id,
        content_type=ContentType(body.content_type.value),
        reason=body.reason or "manual_checkpoint",
        actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
    )
    if version is None:
        raise HTTPException(status_code=404, detail="No current version to checkpoint")
    session.commit()
    session.refresh(version)
    return VersionResponse.model_validate(version)


@router.get("/{lesson_hashid}/audit-log", response_model=List[AuditLogResponse])
def get_lesson_timeline(
    lesson_hashid: str,
    limit: int = Query(100, le=200),
    before_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["viewer", "reader", "editor", "publisher", "admin"])),
):
    lesson_id = decode_id(lesson_hashid)
    _deny_history_for_viewer(claims)
    _require_lesson_access(lesson_id, claims, session)
    rows = get_lesson_audit_log(session, lesson_id=lesson_id, limit=limit, before_id=before_id)
    return [AuditLogResponse.model_validate(row) for row in rows]




# ── Audio URL ─────────────────────────────────────────────────────────────────

@router.get("/{lesson_hashid}/audio-url")
def get_lesson_audio_url(lesson_hashid: str, session: Session = Depends(get_session)):
    """Get a presigned URL for a lesson audio file."""
    from storage import create_presigned_audio_url, get_audio_object_key, s3_enabled

    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not s3_enabled():
        raise HTTPException(status_code=500, detail="S3 is not configured")

    audio_key = get_audio_object_key(lesson_id, lesson.filename)
    presigned_url = create_presigned_audio_url(audio_key)
    if not presigned_url:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return {"url": presigned_url}


# ── Exports ───────────────────────────────────────────────────────────────────

@router.get("/{lesson_hashid}/exports/{export_type}")
def export_lesson(
    lesson_hashid: str,
    export_type: str,
    format: str = Query("pdf", regex="^(md|docx|pdf)$"),  # noqa: A002
    include_fields: Optional[List[str]] = Query(None),
    transcript_type: Literal["corrected", "initial"] = Query("corrected"),
    lang: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """Generate lesson export (summary, edited, transcript) in md/docx/pdf."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if export_type not in {"summary", "edited", "transcript", "sources", "sources_detailed"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported export_type. Allowed values: "
                "summary, edited, transcript, sources, sources_detailed"
            ),
        )

    payload, filename, media_type = export_service.generate_lesson_export(
        session=session,
        lesson=lesson,
        export_type=export_type,
        export_format=format,  # type: ignore[arg-type]
        include_fields=include_fields,
        transcript_type=transcript_type,
        language=lang,
    )
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{lesson_hashid}/imports/{import_type}", response_model=LessonResponse)
async def import_lesson_document(
    lesson_hashid: str,
    import_type: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Import lesson content (summary, edited, transcript) from md/docx."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    _require_lesson_access(lesson_id, claims, session)

    if import_type not in {"summary", "edited", "transcript"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported import_type. Allowed values: summary, edited, transcript",
        )

    filename = str(file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    markdown = export_service.document_bytes_to_markdown(payload, filename=filename)
    imported_content = export_service.extract_markdown_main_section(markdown).strip()
    if not imported_content:
        raise HTTPException(status_code=400, detail="Imported document is empty")

    actor_id = claims.get("sub")
    if import_type == "summary":
        updated = lesson_service.update_lesson_data(
            lesson_id,
            LessonUpdate(summary=imported_content),
            session,
            assigned_by=actor_id,
        )
        if updated.edited_transcript:
            updated = lesson_service.realign_summary_alignment(lesson_id=lesson_id, session=session)
        return updated

    if import_type == "edited":
        if not (lesson.corrected_transcript or lesson.transcript):
            raise HTTPException(status_code=400, detail="Cannot import edited version without transcript")
        lesson_service.update_lesson_data(
            lesson_id,
            LessonUpdate(edited_transcript={"markdown": imported_content}),
            session,
            assigned_by=actor_id,
        )
        updated = lesson_service.realign_edited_markdown(
            lesson_id=lesson_id,
            session=session,
            actor={"sub": actor_id, "role": _extract_role(claims)},
        )
        if updated.summary:
            updated = lesson_service.realign_summary_alignment(lesson_id=lesson_id, session=session)
        return updated

    # import_type == "transcript"
    transcript_rows = export_service.transcript_markdown_to_segments(imported_content)
    updated = lesson_service.update_lesson_data(
        lesson_id,
        LessonUpdate(corrected_transcript=transcript_rows),
        session,
        assigned_by=actor_id,
    )
    if updated.edited_transcript:
        updated = lesson_service.realign_edited_markdown(
            lesson_id=lesson_id,
            session=session,
            actor={"sub": actor_id, "role": _extract_role(claims)},
        )
        if updated.summary:
            updated = lesson_service.realign_summary_alignment(lesson_id=lesson_id, session=session)
    return updated

