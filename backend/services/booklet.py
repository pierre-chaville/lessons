"""Business logic for booklet CRUD and composition."""

from __future__ import annotations

import os
import threading
from io import BytesIO
from html import escape
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import func
from sqlmodel import Session, select

from config import load_config
from models import (
    Booklet,
    BookletGeneration,
    BookletItem,
    BookletItemType,
    BookletStatus,
    ContentVersion,
    Course,
    GenerationFormat,
    GenerationStatus,
    Lesson,
    Theme,
)
from services.audit import log_event

ALLOWED_TEMPLATE_FIELDS = {
    "title",
    "date",
    "duration",
    "corrected_transcript",
    "edited_transcript",
    "brief",
    "summary",
    "status",
    "themes",
    "course",
}

TEMPLATE_FIELD_LABELS = {
    "title": "Title",
    "date": "Date",
    "duration": "Duration",
    "corrected_transcript": "Corrected transcript",
    "edited_transcript": "Edited transcript",
    "brief": "Brief",
    "summary": "Summary",
    "status": "Status",
    "themes": "Themes",
    "course": "Course",
}

PDF_FIELD_LABELS = {
    "en": {
        "brief": "Brief",
        "summary": "Summary",
        "edited_transcript": "Edited",
        "corrected_transcript": "Transcript",
    },
    "fr": {
        "brief": "Résumé bref",
        "summary": "Résumé",
        "edited_transcript": "Édition",
        "corrected_transcript": "Transcription",
    },
}


def _actor_user_id(actor: Any) -> Optional[str]:
    if actor is None:
        return None
    if isinstance(actor, dict):
        raw = actor.get("sub")
        if raw is None:
            return None
        return str(raw)
    raw = getattr(actor, "id", None)
    if raw is None:
        return None
    return str(raw)


def _actor_role(actor: Any) -> str:
    if actor is None:
        return "system"
    if isinstance(actor, dict):
        role = actor.get("role")
        if role:
            return str(role).lower()
        metadata = actor.get("public_metadata") or {}
        if isinstance(metadata, dict) and metadata.get("role"):
            return str(metadata["role"]).lower()
        return "unknown"
    return str(getattr(actor, "role", "unknown")).lower()


def _enum_value(raw: Any) -> str:
    return str(getattr(raw, "value", raw))


def _get_booklet(session: Session, booklet_id: int) -> Booklet:
    booklet = session.get(Booklet, booklet_id)
    if booklet is None:
        raise HTTPException(status_code=404, detail="Booklet not found")
    return booklet


def get_booklet(session: Session, booklet_id: int) -> Booklet:
    return _get_booklet(session, booklet_id)


def _require_composition_unlocked(booklet: Booklet) -> None:
    if booklet.status in (BookletStatus.READY, BookletStatus.ARCHIVED):
        raise HTTPException(
            status_code=409,
            detail="Booklet composition is locked in ready/archived status",
        )


def _sorted_booklet_items(session: Session, booklet_id: int) -> List[BookletItem]:
    statement = (
        select(BookletItem)
        .where(BookletItem.booklet_id == booklet_id)
        .order_by(BookletItem.position, BookletItem.id)
    )
    return list(session.exec(statement).all())


def _renumber_contiguous(session: Session, booklet_id: int) -> None:
    rows = _sorted_booklet_items(session, booklet_id)
    for idx, row in enumerate(rows, start=1):
        if row.position != idx:
            row.position = idx
            session.add(row)
    session.flush()


def _normalize_template_data(raw: Any) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="template_data must be an array of field names")
    result: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="template_data must contain only string field names")
        key = value.strip()
        if not key:
            continue
        if key not in ALLOWED_TEMPLATE_FIELDS:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Invalid template_data field: {key}",
                    "allowed_fields": sorted(ALLOWED_TEMPLATE_FIELDS),
                },
            )
        if key not in result:
            result.append(key)
    return result


def _delete_files_worker(paths: Sequence[str]) -> None:
    for path in paths:
        if not path:
            continue
        # Ignore remote/opaque keys; cleanup is backend-storage specific.
        if "://" in path:
            continue
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                continue


def _delete_files_async(paths: Sequence[str]) -> None:
    if not paths:
        return
    thread = threading.Thread(target=_delete_files_worker, args=(list(paths),), daemon=True)
    thread.start()


def _safe_filename(title: str) -> str:
    return "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip() or "booklet"


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _format_time(seconds: Any) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "00:00"
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"


def _to_paragraph_text(value: Any) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _booklet_pdf_language() -> str:
    try:
        config = load_config()
        language = str((config.get("transcribe") or {}).get("language") or "en").lower()
    except Exception:
        language = "en"
    return "fr" if language.startswith("fr") else "en"


def _stringify_transcript_like(raw: Any) -> str:
    if not isinstance(raw, list):
        return "-"
    lines: List[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).strip()
            start = entry.get("start")
            end = entry.get("end")
            if start is not None and end is not None:
                prefix = f"[{_format_time(start)}-{_format_time(end)}] "
            else:
                prefix = ""
            if text:
                lines.append(prefix + text)
        else:
            lines.append(str(entry))
    return "\n".join(lines).strip() or "-"


def generate_booklet_pdf(session: Session, booklet_id: int) -> tuple[bytes, str]:
    booklet = _get_booklet(session, booklet_id)
    items = _sorted_booklet_items(session, booklet_id)
    lesson_ids = [row.lesson_id for row in items if row.lesson_id is not None]
    lessons = {}
    if lesson_ids:
        lesson_rows = list(session.exec(select(Lesson).where(Lesson.id.in_(lesson_ids))).all())
        lessons = {lesson.id: lesson for lesson in lesson_rows}
    course_ids = {lesson.course_id for lesson in lessons.values() if lesson.course_id is not None}
    courses = {}
    if course_ids:
        course_rows = list(session.exec(select(Course).where(Course.id.in_(course_ids))).all())
        courses = {course.id: course for course in course_rows}
    theme_ids = {theme_id for lesson in lessons.values() for theme_id in lesson.get_themes()}
    themes = {}
    if theme_ids:
        theme_rows = list(session.exec(select(Theme).where(Theme.id.in_(theme_ids))).all())
        themes = {theme.id: theme for theme in theme_rows}

    styles = getSampleStyleSheet()
    pdf_language = _booklet_pdf_language()
    localized_labels = PDF_FIELD_LABELS.get(pdf_language, PDF_FIELD_LABELS["en"])
    title_style = ParagraphStyle(
        "BookletTitle",
        parent=styles["Heading1"],
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#4f46e5"),
        spaceAfter=10,
    )
    subtitle_style = ParagraphStyle(
        "BookletSubtitle",
        parent=styles["Heading2"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#374151"),
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ItemHeading",
        parent=styles["Heading2"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
    )
    label_style = ParagraphStyle(
        "FieldLabel",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceAfter=2,
    )
    value_style = ParagraphStyle(
        "FieldValue",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#374151"),
        spaceAfter=8,
    )

    story: List[Any] = []
    # Cover page
    story.append(Paragraph(_to_paragraph_text(booklet.title), title_style))
    if booklet.subtitle:
        story.append(Paragraph(_to_paragraph_text(booklet.subtitle), subtitle_style))
    if booklet.description:
        story.append(Paragraph(_to_paragraph_text(booklet.description), value_style))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"Status: {_enum_value(booklet.status)}", value_style))
    story.append(PageBreak())

    selected_fields = booklet.template_data or []
    ordered_fields = [
        field
        for field in (
            "title",
            "date",
            "duration",
            "course",
            "themes",
            "status",
            "brief",
            "summary",
            "edited_transcript",
            "corrected_transcript",
        )
        if field in selected_fields
    ]
    for idx, item in enumerate(items):
        if idx > 0:
            story.append(PageBreak())

        if item.item_type == BookletItemType.CHAPTER:
            chapter_title = item.chapter_title or "Chapter"
            story.append(Paragraph(_to_paragraph_text(chapter_title), heading_style))
            if item.chapter_subtitle:
                story.append(Paragraph(_to_paragraph_text(item.chapter_subtitle), subtitle_style))
            if item.chapter_body:
                story.append(Paragraph(_to_paragraph_text(item.chapter_body), value_style))
            story.append(Paragraph(f"Starts new page: {'Yes' if item.chapter_starts_new_page else 'No'}", value_style))
            continue

        if item.lesson_id is None:
            story.append(Paragraph("Lesson item without lesson reference", value_style))
            continue

        lesson = lessons.get(item.lesson_id)
        if lesson is None:
            story.append(Paragraph(f"Lesson #{item.lesson_id} not found", value_style))
            continue

        lesson_title = item.custom_title or lesson.title
        story.append(Paragraph(_to_paragraph_text(lesson_title), heading_style))
        if item.custom_intro:
            story.append(Paragraph(_to_paragraph_text(item.custom_intro), value_style))

        date_selected = "date" in ordered_fields
        duration_selected = "duration" in ordered_fields
        if date_selected or duration_selected:
            date_value = lesson.date.isoformat() if lesson.date else "-"
            duration_value = _format_duration(lesson.duration) if duration_selected else "-"
            if date_selected and duration_selected:
                story.append(Paragraph(_to_paragraph_text(f"{date_value} / {duration_value}"), value_style))
            elif date_selected:
                story.append(Paragraph(_to_paragraph_text(date_value), value_style))
            else:
                story.append(Paragraph(_to_paragraph_text(duration_value), value_style))

        for field in ordered_fields:
            if field in {"date", "duration"}:
                continue
            if field == "title":
                value = lesson.title or "-"
            elif field == "corrected_transcript":
                value = _stringify_transcript_like(lesson.corrected_transcript)
            elif field == "edited_transcript":
                value = _stringify_transcript_like(lesson.edited_transcript)
            elif field == "brief":
                value = lesson.brief or "-"
            elif field == "summary":
                value = lesson.summary or "-"
            elif field == "status":
                value = lesson.status or "-"
            elif field == "themes":
                theme_ids = lesson.get_themes()
                names = [themes[tid].name for tid in theme_ids if tid in themes]
                value = ", ".join(names) if names else "-"
            elif field == "course":
                course = courses.get(lesson.course_id) if lesson.course_id is not None else None
                value = course.name if course else "-"
            else:
                continue

            if field in {"brief", "summary", "edited_transcript", "corrected_transcript"}:
                label = localized_labels.get(field, TEMPLATE_FIELD_LABELS.get(field, field))
                story.append(Paragraph(f"<b>{_to_paragraph_text(label)}</b>", label_style))
            story.append(Paragraph(_to_paragraph_text(value), value_style))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=booklet.title,
    )
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes, f"{_safe_filename(booklet.title)}.pdf"


def create_booklet(session: Session, data: Dict[str, Any], actor: Any) -> Booklet:
    booklet = Booklet(
        title=data["title"],
        subtitle=data.get("subtitle"),
        description=data.get("description"),
        cover_metadata=data.get("cover_metadata") or {},
        template=data.get("template") or "default",
        course_id=data.get("course_id"),
        template_data=_normalize_template_data(data.get("template_data")),
        created_by_id=_actor_user_id(actor),
    )
    session.add(booklet)
    session.flush()
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet.id),
        action="booklet.created",
        payload={"title": booklet.title, "status": _enum_value(booklet.status)},
    )
    session.commit()
    session.refresh(booklet)
    return booklet


def update_booklet(session: Session, booklet_id: int, data: Dict[str, Any], actor: Any) -> Booklet:
    booklet = _get_booklet(session, booklet_id)
    if booklet.status != BookletStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft booklets can be edited")

    before = {
        "title": booklet.title,
        "subtitle": booklet.subtitle,
        "description": booklet.description,
        "cover_metadata": booklet.cover_metadata,
        "template": booklet.template,
        "course_id": booklet.course_id,
        "template_data": booklet.template_data,
    }
    for field in ("title", "subtitle", "description", "cover_metadata", "template", "course_id", "template_data"):
        if field in data:
            if field == "title" and data[field] is None:
                raise HTTPException(status_code=400, detail="title cannot be null")
            if field == "template_data":
                setattr(booklet, field, _normalize_template_data(data[field]))
                continue
            setattr(booklet, field, data[field])
    session.add(booklet)
    session.flush()
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet.id),
        action="booklet.updated",
        payload={"before": before, "after": {
            "title": booklet.title,
            "subtitle": booklet.subtitle,
            "description": booklet.description,
            "cover_metadata": booklet.cover_metadata,
            "template": booklet.template,
            "course_id": booklet.course_id,
            "template_data": booklet.template_data,
        }},
    )
    session.commit()
    session.refresh(booklet)
    return booklet


def delete_booklet(session: Session, booklet_id: int, actor: Any) -> None:
    booklet = _get_booklet(session, booklet_id)
    generation_paths = list(
        session.exec(
            select(BookletGeneration.file_path).where(BookletGeneration.booklet_id == booklet_id)
        ).all()
    )
    session.delete(booklet)
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.deleted",
        payload={"title": booklet.title},
    )
    session.commit()
    _delete_files_async([p for p in generation_paths if p])


def _shift_positions_from(session: Session, booklet_id: int, start_position: int) -> None:
    to_shift = list(
        session.exec(
            select(BookletItem)
            .where(
                BookletItem.booklet_id == booklet_id,
                BookletItem.position >= start_position,
            )
            .order_by(BookletItem.position.desc())
        ).all()
    )
    for row in to_shift:
        row.position += 1
        session.add(row)


def _target_position(session: Session, booklet_id: int, position: Optional[int]) -> int:
    if position is None:
        max_pos = session.exec(
            select(func.coalesce(func.max(BookletItem.position), 0)).where(
                BookletItem.booklet_id == booklet_id
            )
        ).one()
        return int(max_pos) + 1
    if position <= 0:
        raise HTTPException(status_code=400, detail="position must be >= 1")
    _shift_positions_from(session, booklet_id, position)
    return position


def add_item(session: Session, booklet_id: int, data: Dict[str, Any], actor: Any) -> BookletItem:
    booklet = _get_booklet(session, booklet_id)
    _require_composition_unlocked(booklet)
    item_type = BookletItemType(data["item_type"])
    target_position = _target_position(session, booklet_id, data.get("position"))
    lesson_id = data.get("lesson_id")
    if item_type == BookletItemType.LESSON:
        if lesson_id is None:
            raise HTTPException(status_code=400, detail="lesson_id is required for lesson items")
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found")
        duplicate = session.exec(
            select(BookletItem.id).where(
                BookletItem.booklet_id == booklet_id,
                BookletItem.item_type == BookletItemType.LESSON,
                BookletItem.lesson_id == lesson_id,
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Lesson is already in this booklet")
    else:
        lesson_id = None

    row = BookletItem(
        booklet_id=booklet_id,
        position=target_position,
        item_type=item_type,
        lesson_id=lesson_id,
        custom_title=data.get("custom_title"),
        custom_intro=data.get("custom_intro"),
        include_brief=bool(data.get("include_brief", False)),
        chapter_title=data.get("chapter_title"),
        chapter_subtitle=data.get("chapter_subtitle"),
        chapter_body=data.get("chapter_body"),
        chapter_starts_new_page=bool(data.get("chapter_starts_new_page", True)),
        added_by_id=_actor_user_id(actor),
    )
    session.add(row)
    session.flush()
    _renumber_contiguous(session, booklet_id)
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.item_added",
        payload={"item_id": row.id, "item_type": _enum_value(row.item_type), "position": target_position},
    )
    session.commit()
    session.refresh(row)
    return row


def add_lesson(
    session: Session,
    booklet_id: int,
    lesson_id: int,
    actor: Any,
    position: Optional[int] = None,
    custom_title: Optional[str] = None,
    custom_intro: Optional[str] = None,
    include_brief: bool = False,
) -> BookletItem:
    return add_item(
        session=session,
        booklet_id=booklet_id,
        data={
            "item_type": _enum_value(BookletItemType.LESSON),
            "lesson_id": lesson_id,
            "position": position,
            "custom_title": custom_title,
            "custom_intro": custom_intro,
            "include_brief": include_brief,
        },
        actor=actor,
    )


def remove_item(session: Session, booklet_id: int, item_id: int, actor: Any) -> None:
    booklet = _get_booklet(session, booklet_id)
    _require_composition_unlocked(booklet)
    row = session.get(BookletItem, item_id)
    if row is None or row.booklet_id != booklet_id:
        raise HTTPException(status_code=404, detail="Item not in booklet")
    old_position = row.position
    session.delete(row)
    session.flush()
    _renumber_contiguous(session, booklet_id)
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.item_removed",
        payload={"item_id": item_id, "item_type": _enum_value(row.item_type), "old_position": old_position},
    )
    session.commit()


def remove_lesson(session: Session, booklet_id: int, lesson_id: int, actor: Any) -> None:
    row = session.exec(
        select(BookletItem).where(
            BookletItem.booklet_id == booklet_id,
            BookletItem.item_type == BookletItemType.LESSON,
            BookletItem.lesson_id == lesson_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lesson not in booklet")
    remove_item(session, booklet_id, row.id, actor)


def update_item(
    session: Session,
    booklet_id: int,
    item_id: int,
    data: Dict[str, Any],
    actor: Any,
) -> BookletItem:
    booklet = _get_booklet(session, booklet_id)
    _require_composition_unlocked(booklet)
    row = session.get(BookletItem, item_id)
    if row is None or row.booklet_id != booklet_id:
        raise HTTPException(status_code=404, detail="Item not in booklet")

    allowed_fields = (
        "custom_title",
        "custom_intro",
        "include_brief",
        "chapter_title",
        "chapter_subtitle",
        "chapter_body",
        "chapter_starts_new_page",
        "is_included",
    )
    before = {field: getattr(row, field) for field in allowed_fields}
    for field in allowed_fields:
        if field in data:
            setattr(row, field, data[field])
    if row.item_type == BookletItemType.LESSON:
        row.chapter_title = None
        row.chapter_subtitle = None
        row.chapter_body = None
    if row.item_type == BookletItemType.CHAPTER:
        row.lesson_id = None
        row.include_brief = False

    session.add(row)
    session.flush()
    after = {field: getattr(row, field) for field in allowed_fields}
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.item_updated",
        payload={"item_id": item_id, "item_type": _enum_value(row.item_type), "before": before, "after": after},
    )
    session.commit()
    session.refresh(row)
    return row


def update_lesson_in_booklet(
    session: Session,
    booklet_id: int,
    lesson_id: int,
    data: Dict[str, Any],
    actor: Any,
) -> BookletItem:
    row = session.exec(
        select(BookletItem).where(
            BookletItem.booklet_id == booklet_id,
            BookletItem.item_type == BookletItemType.LESSON,
            BookletItem.lesson_id == lesson_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lesson not in booklet")
    return update_item(session, booklet_id, row.id, data, actor)


def reorder(session: Session, booklet_id: int, ordered_item_ids: List[int], actor: Any) -> List[BookletItem]:
    booklet = _get_booklet(session, booklet_id)
    _require_composition_unlocked(booklet)
    rows = _sorted_booklet_items(session, booklet_id)
    existing_ids = [row.id for row in rows if row.id is not None]
    if set(existing_ids) != set(ordered_item_ids) or len(existing_ids) != len(ordered_item_ids):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "item_ids must be a permutation of existing booklet items",
                "existing": existing_ids,
                "provided": ordered_item_ids,
            },
        )
    if len(set(ordered_item_ids)) != len(ordered_item_ids):
        raise HTTPException(status_code=400, detail="item_ids contains duplicates")

    by_item_id = {row.id: row for row in rows}
    before = existing_ids
    for idx, item_id in enumerate(ordered_item_ids, start=1):
        row = by_item_id[item_id]
        row.position = idx
        session.add(row)
    session.flush()
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.reordered",
        payload={"before": before, "after": ordered_item_ids},
    )
    session.commit()
    return _sorted_booklet_items(session, booklet_id)


def change_status(
    session: Session,
    booklet_id: int,
    new_status: BookletStatus,
    actor: Any,
    reason: Optional[str] = None,
) -> Booklet:
    booklet = _get_booklet(session, booklet_id)
    old = booklet.status
    old_status = _enum_value(old)
    new_status_value = _enum_value(new_status)
    role = _actor_role(actor)

    allowed = False
    if old == BookletStatus.DRAFT and new_status == BookletStatus.READY:
        allowed = role in {"publisher", "admin"}
    elif old == BookletStatus.READY and new_status == BookletStatus.DRAFT:
        allowed = role in {"publisher", "admin"}
    elif new_status == BookletStatus.ARCHIVED:
        allowed = role == "admin"

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Transition from {old_status} to {new_status_value} is not allowed for role {role}",
        )

    if old == BookletStatus.DRAFT and new_status == BookletStatus.READY:
        offenders = list(
            session.exec(
                select(BookletItem.lesson_id)
                .join(Lesson, Lesson.id == BookletItem.lesson_id)
                .where(
                    BookletItem.booklet_id == booklet_id,
                    BookletItem.item_type == BookletItemType.LESSON,
                    BookletItem.is_included == True,  # noqa: E712
                    Lesson.status != "validated",
                )
                .order_by(BookletItem.position)
            ).all()
        )
        if offenders:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "All included lessons must be validated before ready",
                    "lesson_ids": offenders,
                },
            )

    booklet.status = new_status
    session.add(booklet)
    session.flush()
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.status_changed",
        payload={"from": old_status, "to": new_status_value, "reason": reason},
    )
    session.commit()
    session.refresh(booklet)
    return booklet


def get_booklet_items(session: Session, booklet_id: int) -> List[BookletItem]:
    _get_booklet(session, booklet_id)
    return _sorted_booklet_items(session, booklet_id)


def get_booklet_lessons(session: Session, booklet_id: int) -> List[BookletItem]:
    return [
        row
        for row in get_booklet_items(session, booklet_id)
        if row.item_type == BookletItemType.LESSON and row.lesson_id is not None
    ]


def list_booklets(
    session: Session,
    status: Optional[BookletStatus] = None,
    search: Optional[str] = None,
    course_id: Optional[int] = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[List[Booklet], int]:
    statement = select(Booklet)
    count_statement = select(func.count(Booklet.id))
    if status:
        statement = statement.where(Booklet.status == status)
        count_statement = count_statement.where(Booklet.status == status)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(Booklet.title.ilike(pattern))
        count_statement = count_statement.where(Booklet.title.ilike(pattern))
    if course_id is not None:
        statement = statement.where(Booklet.course_id == course_id)
        count_statement = count_statement.where(Booklet.course_id == course_id)
    total = int(session.exec(count_statement).one())
    rows = list(
        session.exec(
            statement.order_by(Booklet.created_at.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def request_generation(
    session: Session,
    booklet_id: int,
    render_format: GenerationFormat,
    parameters: Dict[str, Any],
    actor: Any,
) -> BookletGeneration:
    booklet = _get_booklet(session, booklet_id)
    role = _actor_role(actor)
    if booklet.status == BookletStatus.READY and role not in {"publisher", "admin"}:
        raise HTTPException(status_code=403, detail="Ready booklet generation requires publisher role")
    if booklet.status == BookletStatus.ARCHIVED:
        raise HTTPException(status_code=409, detail="Archived booklet cannot be generated")
    if render_format == GenerationFormat.DOCX:
        raise HTTPException(status_code=501, detail="DOCX generation is not implemented yet")

    generation = BookletGeneration(
        booklet_id=booklet_id,
        status=GenerationStatus.PENDING,
        format=render_format,
        requested_by_id=_actor_user_id(actor),
        parameters=parameters or {},
    )
    session.add(generation)
    session.flush()
    session.commit()
    session.refresh(generation)
    return generation


def list_generations(session: Session, booklet_id: int) -> List[BookletGeneration]:
    _get_booklet(session, booklet_id)
    return list(
        session.exec(
            select(BookletGeneration)
            .where(BookletGeneration.booklet_id == booklet_id)
            .order_by(BookletGeneration.requested_at.desc())
        ).all()
    )


def get_generation(session: Session, booklet_id: int, generation_id: UUID) -> BookletGeneration:
    _get_booklet(session, booklet_id)
    row = session.get(BookletGeneration, generation_id)
    if row is None or row.booklet_id != booklet_id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return row


def delete_generation(session: Session, booklet_id: int, generation_id: UUID, actor: Any) -> None:
    row = get_generation(session, booklet_id, generation_id)
    path = row.file_path
    session.delete(row)
    session.flush()
    log_event(
        session=session,
        actor=actor,
        entity_type="booklet",
        entity_id=str(booklet_id),
        action="booklet.generation_deleted",
        payload={"generation_id": str(generation_id)},
    )
    session.commit()
    if path:
        _delete_files_async([path])


def preview_html(session: Session, booklet_id: int) -> str:
    booklet = _get_booklet(session, booklet_id)
    rows = _sorted_booklet_items(session, booklet_id)
    lesson_ids = [r.lesson_id for r in rows if r.item_type == BookletItemType.LESSON and r.lesson_id]
    lessons = {}
    if lesson_ids:
        lesson_rows = list(session.exec(select(Lesson).where(Lesson.id.in_(lesson_ids))).all())
        lessons = {row.id: row for row in lesson_rows}
    html_parts = [
        "<html><head><meta charset='utf-8'><title>Booklet Preview</title></head><body>",
        f"<h1>{booklet.title}</h1>",
    ]
    if booklet.subtitle:
        html_parts.append(f"<h2>{booklet.subtitle}</h2>")
    if booklet.description:
        html_parts.append(f"<p>{booklet.description}</p>")
    for item in rows:
        if not item.is_included:
            continue
        if item.item_type == BookletItemType.CHAPTER:
            title = item.chapter_title or "Chapter"
            html_parts.append(f"<section><h2>{title}</h2>")
            if item.chapter_subtitle:
                html_parts.append(f"<h3>{item.chapter_subtitle}</h3>")
            if item.chapter_body:
                html_parts.append(f"<p>{item.chapter_body}</p>")
            html_parts.append("</section>")
            continue
        if not item.lesson_id:
            continue
        lesson = lessons.get(item.lesson_id)
        if lesson is None:
            continue
        display_title = item.custom_title or lesson.title
        html_parts.append(f"<section><h3>{display_title}</h3>")
        if item.custom_intro:
            html_parts.append(f"<p>{item.custom_intro}</p>")
        if lesson.summary:
            html_parts.append(f"<p>{lesson.summary}</p>")
        if item.include_brief and lesson.brief:
            html_parts.append(f"<p><em>{lesson.brief}</em></p>")
        html_parts.append("</section>")
    html_parts.append("</body></html>")
    return "".join(html_parts)


def build_generation_snapshot(session: Session, booklet_id: int) -> Dict[str, Any]:
    booklet = _get_booklet(session, booklet_id)
    rows = _sorted_booklet_items(session, booklet_id)
    items_payload: List[Dict[str, Any]] = []
    for row in rows:
        if row.item_type == BookletItemType.CHAPTER:
            items_payload.append(
                {
                    "item_id": row.id,
                    "item_type": _enum_value(row.item_type),
                    "position": row.position,
                    "chapter_title": row.chapter_title,
                    "chapter_subtitle": row.chapter_subtitle,
                    "chapter_body": row.chapter_body,
                    "chapter_starts_new_page": row.chapter_starts_new_page,
                    "is_included": row.is_included,
                }
            )
            continue
        if not row.lesson_id:
            continue
        title_ver = session.exec(
            select(ContentVersion.id)
            .where(
                ContentVersion.lesson_id == row.lesson_id,
                ContentVersion.content_type == "title",
                ContentVersion.is_current == True,  # noqa: E712
            )
        ).first()
        summary_ver = session.exec(
            select(ContentVersion.id)
            .where(
                ContentVersion.lesson_id == row.lesson_id,
                ContentVersion.content_type == "summary",
                ContentVersion.is_current == True,  # noqa: E712
            )
        ).first()
        brief_ver = session.exec(
            select(ContentVersion.id)
            .where(
                ContentVersion.lesson_id == row.lesson_id,
                ContentVersion.content_type == "brief",
                ContentVersion.is_current == True,  # noqa: E712
            )
        ).first()
        items_payload.append(
            {
                "item_id": row.id,
                "item_type": _enum_value(row.item_type),
                "lesson_id": row.lesson_id,
                "position": row.position,
                "title_version_id": str(title_ver) if title_ver else None,
                "summary_version_id": str(summary_ver) if summary_ver else None,
                "brief_version_id": str(brief_ver) if brief_ver else None,
                "custom_title": row.custom_title,
                "custom_intro": row.custom_intro,
                "include_brief": row.include_brief,
                "is_included": row.is_included,
            }
        )
    return {
        "booklet_meta": {
            "title": booklet.title,
            "subtitle": booklet.subtitle,
            "description": booklet.description,
            "cover_metadata": booklet.cover_metadata,
            "template": booklet.template,
        },
        "items": items_payload,
    }
