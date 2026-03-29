"""Lessons router — /lessons endpoints including PDF and audio URL."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session
from typing import List, Dict, Any, Optional

import crud
from auth import require_auth, require_roles, _extract_roles, _extract_role
from database import get_session
from schemas.lesson import (
    LessonCreate, LessonUpdate, LessonListResponse, LessonResponse,
    StatusUpdate, ALLOWED_TRANSITIONS, VALID_STATUSES,
)
from services import lessons as lesson_service
from services import pdf as pdf_service
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


@router.get("", response_model=List[LessonListResponse])
def get_lessons(
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    session: Session = Depends(get_session),
):
    """Get all lessons (lightweight response), optionally filtered by course."""
    lessons = crud.get_all_lessons(session, course_id=course_id)
    return [lesson_service.build_lesson_list_item(lesson, session) for lesson in lessons]


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

    lesson.status = target
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
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


@router.delete("/{lesson_hashid}", status_code=204)
def delete_lesson(
    lesson_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a lesson."""
    lesson_id = decode_id(lesson_hashid)
    if not crud.delete_lesson(session, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    return None


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


# ── PDF exports ───────────────────────────────────────────────────────────────

@router.get("/{lesson_hashid}/pdf/summary")
def get_lesson_summary_pdf(lesson_hashid: str, session: Session = Depends(get_session)):
    """Generate and download PDF of the lesson summary."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.summary:
        raise HTTPException(status_code=404, detail="No summary available")

    pdf_bytes, filename = pdf_service.generate_summary_pdf(lesson)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lesson_hashid}/pdf/transcript")
def get_lesson_transcript_pdf(
    lesson_hashid: str,
    transcript_type: str = Query("corrected", regex="^(corrected|initial)$"),
    session: Session = Depends(get_session),
):
    """Generate and download PDF of the lesson transcript (without timestamps)."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    transcript = (
        lesson.corrected_transcript
        if transcript_type == "corrected"
        else lesson.transcript
    )
    if not transcript or len(transcript) == 0:
        raise HTTPException(
            status_code=404, detail=f"No {transcript_type} transcript available"
        )

    pdf_bytes, filename = pdf_service.generate_transcript_pdf(lesson, transcript_type)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lesson_hashid}/pdf/edited")
def get_lesson_edited_transcript_pdf(
    lesson_hashid: str, session: Session = Depends(get_session)
):
    """Generate and download PDF of the edited transcript with sources."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.edited_transcript or len(lesson.edited_transcript) == 0:
        raise HTTPException(status_code=404, detail="No edited transcript available")

    pdf_bytes, filename = pdf_service.generate_edited_pdf(lesson, session)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lesson_hashid}/pdf/sources")
def get_lesson_sources_pdf(lesson_hashid: str, session: Session = Depends(get_session)):
    """Generate and download PDF of all sources grouped by author."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.edited_transcript or len(lesson.edited_transcript) == 0:
        raise HTTPException(status_code=404, detail="No sources available")

    pdf_bytes, filename = pdf_service.generate_sources_pdf(lesson, session)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lesson_hashid}/pdf/sources/detailed")
def get_lesson_detailed_sources_pdf(
    lesson_hashid: str, session: Session = Depends(get_session)
):
    """Generate and download detailed PDF of all sources with full information."""
    lesson_id = decode_id(lesson_hashid)
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    if not lesson.edited_transcript or len(lesson.edited_transcript) == 0:
        raise HTTPException(status_code=404, detail="No sources available")

    pdf_bytes, filename = pdf_service.generate_detailed_sources_pdf(lesson, session)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
