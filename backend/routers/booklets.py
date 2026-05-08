"""Booklets router — /booklets endpoints."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlmodel import Session, select

from auth import _extract_role, require_roles
from database import get_session
from models import BookletStatus, GenerationFormat, Lesson
from schemas.booklet import (
    BookletCreate,
    BookletDetailResponse,
    BookletGenerationCreate,
    BookletGenerationResponse,
    BookletItemAdd,
    BookletItemResponse,
    BookletItemUpdate,
    BookletLessonAdd,
    BookletLessonUpdate,
    BookletListResponse,
    BookletReorderRequest,
    BookletResponse,
    BookletStatusChangeRequest,
    BookletUpdate,
)
from services import booklet as booklet_service

router = APIRouter(prefix="/booklets", tags=["Booklets"])


def _actor_from_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    return {"sub": claims.get("sub"), "role": _extract_role(claims)}


def _lesson_meta_by_ids(session: Session, lesson_ids: List[int]) -> Dict[int, Lesson]:
    if not lesson_ids:
        return {}
    rows = list(session.exec(select(Lesson).where(Lesson.id.in_(lesson_ids))).all())
    return {row.id: row for row in rows}


def _as_booklet_item_response(
    row,
    lesson_title: Optional[str] = None,
    lesson_status: Optional[str] = None,
) -> BookletItemResponse:
    return BookletItemResponse(
        id=row.id,
        booklet_id=row.booklet_id,
        position=row.position,
        item_type=row.item_type,
        lesson_id=row.lesson_id,
        custom_title=row.custom_title,
        custom_intro=row.custom_intro,
        include_brief=row.include_brief,
        chapter_title=row.chapter_title,
        chapter_subtitle=row.chapter_subtitle,
        chapter_body=row.chapter_body,
        chapter_starts_new_page=row.chapter_starts_new_page,
        is_included=row.is_included,
        added_at=row.added_at,
        added_by_id=row.added_by_id,
        lesson_title=lesson_title,
        lesson_status=lesson_status,
    )


@router.get("", response_model=BookletListResponse)
def get_booklets(
    status: Optional[BookletStatus] = Query(None),
    search: Optional[str] = Query(None),
    course_id: Optional[int] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    items, total = booklet_service.list_booklets(
        session=session,
        status=status,
        search=search,
        course_id=course_id,
        offset=offset,
        limit=limit,
    )
    return BookletListResponse(
        items=[BookletResponse.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=BookletResponse, status_code=201)
def create_booklet(
    body: BookletCreate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.create_booklet(session, body.model_dump(), _actor_from_claims(claims))
    return BookletResponse.model_validate(row)


@router.get("/{booklet_id}", response_model=BookletDetailResponse)
def get_booklet(
    booklet_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    booklet = booklet_service.get_booklet(session, booklet_id)
    rows = booklet_service.get_booklet_items(session, booklet_id)
    lesson_ids = [r.lesson_id for r in rows if r.lesson_id]
    meta = _lesson_meta_by_ids(session, lesson_ids)
    items = [
        _as_booklet_item_response(
            r,
            lesson_title=meta.get(r.lesson_id).title if meta.get(r.lesson_id) else None,
            lesson_status=meta.get(r.lesson_id).status if meta.get(r.lesson_id) else None,
        )
        for r in rows
    ]
    lesson_items = [item for item in items if item.item_type.value == "lesson"]
    return BookletDetailResponse(
        **BookletResponse.model_validate(booklet).model_dump(),
        items=items,
        lessons=lesson_items,
    )


@router.patch("/{booklet_id}", response_model=BookletResponse)
def update_booklet(
    booklet_id: int,
    body: BookletUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.update_booklet(
        session=session,
        booklet_id=booklet_id,
        data=body.model_dump(exclude_unset=True),
        actor=_actor_from_claims(claims),
    )
    return BookletResponse.model_validate(row)


@router.delete("/{booklet_id}", status_code=204)
def delete_booklet(
    booklet_id: int,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    booklet_service.delete_booklet(session, booklet_id, _actor_from_claims(claims))
    return None


@router.post("/{booklet_id}/items", response_model=BookletItemResponse, status_code=201)
def add_item_to_booklet(
    booklet_id: int,
    body: BookletItemAdd,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.add_item(
        session=session,
        booklet_id=booklet_id,
        data=body.model_dump(exclude_unset=True),
        actor=_actor_from_claims(claims),
    )
    lesson = session.get(Lesson, row.lesson_id) if row.lesson_id else None
    return _as_booklet_item_response(
        row,
        lesson_title=lesson.title if lesson else None,
        lesson_status=lesson.status if lesson else None,
    )


@router.patch("/{booklet_id}/items/{item_id}", response_model=BookletItemResponse)
def update_item_in_booklet(
    booklet_id: int,
    item_id: int,
    body: BookletItemUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.update_item(
        session=session,
        booklet_id=booklet_id,
        item_id=item_id,
        data=body.model_dump(exclude_unset=True),
        actor=_actor_from_claims(claims),
    )
    lesson = session.get(Lesson, row.lesson_id) if row.lesson_id else None
    return _as_booklet_item_response(
        row,
        lesson_title=lesson.title if lesson else None,
        lesson_status=lesson.status if lesson else None,
    )


@router.delete("/{booklet_id}/items/{item_id}", status_code=204)
def remove_item_from_booklet(
    booklet_id: int,
    item_id: int,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    booklet_service.remove_item(
        session=session,
        booklet_id=booklet_id,
        item_id=item_id,
        actor=_actor_from_claims(claims),
    )
    return None


@router.post("/{booklet_id}/lessons", response_model=BookletItemResponse, status_code=201)
def add_lesson_to_booklet(
    booklet_id: int,
    body: BookletLessonAdd,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.add_lesson(
        session=session,
        booklet_id=booklet_id,
        lesson_id=body.lesson_id,
        position=body.position,
        custom_title=body.custom_title,
        custom_intro=body.custom_intro,
        include_brief=body.include_brief,
        actor=_actor_from_claims(claims),
    )
    lesson = session.get(Lesson, row.lesson_id)
    return _as_booklet_item_response(
        row,
        lesson_title=lesson.title if lesson else None,
        lesson_status=lesson.status if lesson else None,
    )


@router.patch("/{booklet_id}/lessons/{lesson_id}", response_model=BookletItemResponse)
def update_lesson_in_booklet(
    booklet_id: int,
    lesson_id: int,
    body: BookletLessonUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.update_lesson_in_booklet(
        session=session,
        booklet_id=booklet_id,
        lesson_id=lesson_id,
        data=body.model_dump(exclude_unset=True),
        actor=_actor_from_claims(claims),
    )
    lesson = session.get(Lesson, row.lesson_id)
    return _as_booklet_item_response(
        row,
        lesson_title=lesson.title if lesson else None,
        lesson_status=lesson.status if lesson else None,
    )


@router.delete("/{booklet_id}/lessons/{lesson_id}", status_code=204)
def remove_lesson_from_booklet(
    booklet_id: int,
    lesson_id: int,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    booklet_service.remove_lesson(
        session=session,
        booklet_id=booklet_id,
        lesson_id=lesson_id,
        actor=_actor_from_claims(claims),
    )
    return None


@router.post("/{booklet_id}/reorder", response_model=List[BookletItemResponse])
def reorder_booklet_lessons(
    booklet_id: int,
    body: BookletReorderRequest,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    ordered_ids = body.item_ids
    if ordered_ids is None and body.lesson_ids is not None:
        lesson_rows = booklet_service.get_booklet_lessons(session, booklet_id)
        by_lesson_id = {r.lesson_id: r.id for r in lesson_rows if r.lesson_id and r.id is not None}
        try:
            ordered_ids = [by_lesson_id[lesson_id] for lesson_id in body.lesson_ids]
        except KeyError:
            raise HTTPException(status_code=400, detail="lesson_ids must reference booklet lesson items")
    if ordered_ids is None:
        raise HTTPException(status_code=400, detail="Provide item_ids (or legacy lesson_ids)")

    rows = booklet_service.reorder(
        session=session,
        booklet_id=booklet_id,
        ordered_item_ids=ordered_ids,
        actor=_actor_from_claims(claims),
    )
    meta = _lesson_meta_by_ids(session, [r.lesson_id for r in rows if r.lesson_id])
    return [
        _as_booklet_item_response(
            r,
            lesson_title=meta.get(r.lesson_id).title if meta.get(r.lesson_id) else None,
            lesson_status=meta.get(r.lesson_id).status if meta.get(r.lesson_id) else None,
        )
        for r in rows
    ]


@router.post("/{booklet_id}/status", response_model=BookletResponse)
def change_booklet_status(
    booklet_id: int,
    body: BookletStatusChangeRequest,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    role = _extract_role(claims)
    if body.new_status == BookletStatus.ARCHIVED and role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can archive a booklet")
    row = booklet_service.change_status(
        session=session,
        booklet_id=booklet_id,
        new_status=body.new_status,
        actor=_actor_from_claims(claims),
        reason=body.reason,
    )
    return BookletResponse.model_validate(row)


@router.get("/{booklet_id}/preview", response_class=HTMLResponse)
def preview_booklet(
    booklet_id: int,
    format: GenerationFormat = Query(GenerationFormat.HTML),  # noqa: A002
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    if format != GenerationFormat.HTML:
        raise HTTPException(status_code=501, detail="Only HTML preview is implemented")
    html = booklet_service.preview_html(session, booklet_id)
    return HTMLResponse(content=html)


@router.post("/{booklet_id}/generate", response_model=BookletGenerationResponse, status_code=201)
def generate_booklet(
    booklet_id: int,
    body: BookletGenerationCreate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.request_generation(
        session=session,
        booklet_id=booklet_id,
        render_format=body.format,
        parameters=body.parameters,
        actor=_actor_from_claims(claims),
    )
    return BookletGenerationResponse.model_validate(row)


@router.get("/{booklet_id}/download-pdf")
def download_booklet_pdf(
    booklet_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    pdf_bytes, filename = booklet_service.generate_booklet_pdf(session, booklet_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{booklet_id}/download-markdown")
def download_booklet_markdown(
    booklet_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    markdown_bytes, filename = booklet_service.generate_booklet_markdown(session, booklet_id)
    return Response(
        content=markdown_bytes,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{booklet_id}/generations", response_model=List[BookletGenerationResponse])
def get_booklet_generations(
    booklet_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    rows = booklet_service.list_generations(session, booklet_id)
    return [BookletGenerationResponse.model_validate(row) for row in rows]


@router.get("/{booklet_id}/generations/{generation_id}", response_model=BookletGenerationResponse)
def get_booklet_generation(
    booklet_id: int,
    generation_id: UUID,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.get_generation(session, booklet_id, generation_id)
    return BookletGenerationResponse.model_validate(row)


@router.get("/{booklet_id}/generations/{generation_id}/download")
def download_booklet_generation(
    booklet_id: int,
    generation_id: UUID,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    row = booklet_service.get_generation(session, booklet_id, generation_id)
    if row.status.value != "success" or not row.file_path:
        raise HTTPException(status_code=404, detail="Generation file is not available")
    if row.file_path.startswith("http://") or row.file_path.startswith("https://"):
        return RedirectResponse(url=row.file_path)
    if not os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="Stored generation file not found")
    filename = os.path.basename(row.file_path)
    media_type = row.file_mime or "application/octet-stream"
    return FileResponse(path=row.file_path, media_type=media_type, filename=filename)


@router.delete("/{booklet_id}/generations/{generation_id}", status_code=204)
def delete_booklet_generation(
    booklet_id: int,
    generation_id: UUID,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    booklet_service.delete_generation(session, booklet_id, generation_id, _actor_from_claims(claims))
    return None
