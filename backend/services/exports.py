"""Unified export generation service (markdown -> docx -> pdf)."""

from __future__ import annotations

import base64
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import httpx
from fastapi import HTTPException
from sqlmodel import Session, select

import crud
from models import Booklet, BookletItem, BookletItemType, Course, Lesson, Theme
from services.edited_transcript import edited_transcript_markdown
from services.markdown_docx import markdown_to_docx_bytes

LessonExportType = Literal["summary", "edited", "transcript", "sources", "sources_detailed"]
BookletExportType = Literal["booklet"]
ExportFormat = Literal["md", "docx", "pdf"]

LESSON_OPTIONAL_FIELDS = {
    "title",
    "date",
    "duration",
    "course_name",
    "themes",
    "brief",
}

BOOKLET_LESSON_OPTIONAL_FIELDS = {
    "date",
    "duration",
    "course_name",
    "themes",
    "brief",
    "summary",
    "edited_version",
}

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"
_MD_MIME = "text/markdown; charset=utf-8"

_I18N_LABELS = {
    "en": {
        "lesson_details": "Lesson details",
        "title_field": "Title",
        "date_field": "Date",
        "duration_field": "Duration",
        "course_field": "Course",
        "themes_field": "Themes",
        "brief_field": "Brief",
        "summary_title": "Summary",
        "edited_title": "Edited version",
        "transcript_title": "Transcript",
        "corrected": "corrected",
        "initial": "initial",
        "sources_title": "Sources",
        "sources_detailed_title": "Detailed sources",
        "no_transcript": "_No transcript available._",
        "no_sources": "_No sources available._",
        "unknown_source_type": "Unknown",
        "source_word": "Source",
        "table_of_contents": "Table of contents",
        "chapter_word": "Chapter",
        "lesson_word": "Lesson",
        "lesson_item_missing": "Lesson item without lesson reference.",
        "lesson_not_found": "Lesson #{lesson_id} not found.",
        "summary_heading": "Summary",
        "edited_heading": "Edited version",
    },
    "fr": {
        "lesson_details": "Details de la session",
        "title_field": "Titre",
        "date_field": "Date",
        "duration_field": "Duree",
        "course_field": "Cours",
        "themes_field": "Themes",
        "brief_field": "Bref resume",
        "summary_title": "Resume",
        "edited_title": "Version redigee",
        "transcript_title": "Transcription",
        "corrected": "corrigee",
        "initial": "initiale",
        "sources_title": "Sources",
        "sources_detailed_title": "Sources detaillees",
        "no_transcript": "_Aucune transcription disponible._",
        "no_sources": "_Aucune source disponible._",
        "unknown_source_type": "Inconnu",
        "source_word": "Source",
        "table_of_contents": "Table des matieres",
        "chapter_word": "Chapitre",
        "lesson_word": "Session",
        "lesson_item_missing": "Element de session sans reference.",
        "lesson_not_found": "Session #{lesson_id} introuvable.",
        "summary_heading": "Resume",
        "edited_heading": "Version redigee",
    },
}


def _normalize_language(language: Optional[str]) -> str:
    value = str(language or "").strip().lower()
    if value.startswith("fr"):
        return "fr"
    return "en"


def _safe_filename(value: str, default: str) -> str:
    cleaned = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in (" ", "-", "_")).rstrip()
    return cleaned or default


def _format_date(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return "-"
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text


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


def _lesson_themes(session: Session, lesson: Lesson) -> str:
    ids = lesson.get_themes()
    if not ids:
        return "-"
    rows = list(session.exec(select(Theme).where(Theme.id.in_(ids))).all())
    by_id = {row.id: row.name for row in rows}
    names = [by_id[idx] for idx in ids if idx in by_id]
    return ", ".join(names) if names else "-"


def _sanitize_lesson_fields(include_fields: Optional[Sequence[str]]) -> List[str]:
    if not include_fields:
        return []
    result: List[str] = []
    for raw in include_fields:
        value = str(raw).strip()
        if not value:
            continue
        if value not in LESSON_OPTIONAL_FIELDS:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Unsupported include_fields value: {value}",
                    "allowed_values": sorted(LESSON_OPTIONAL_FIELDS),
                },
            )
        if value not in result:
            result.append(value)
    return result


def _sanitize_booklet_lesson_fields(include_fields: Optional[Sequence[str]]) -> List[str]:
    if not include_fields:
        return []
    result: List[str] = []
    for raw in include_fields:
        value = str(raw).strip()
        if not value:
            continue
        if value not in BOOKLET_LESSON_OPTIONAL_FIELDS:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Unsupported lesson_fields value: {value}",
                    "allowed_values": sorted(BOOKLET_LESSON_OPTIONAL_FIELDS),
                },
            )
        if value not in result:
            result.append(value)
    return result


def _render_lesson_metadata(
    session: Session,
    lesson: Lesson,
    include_fields: Sequence[str],
    *,
    labels: Dict[str, str],
) -> List[str]:
    if not include_fields:
        return []
    lines: List[str] = []
    lines.append("---")
    if "title" in include_fields:
        lines.append(f"## {lesson.title or '-'}")
        lines.append(f"### {labels['lesson_details']}")
    if "date" in include_fields:
        lines.append(f"- **{labels['date_field']}:** {_format_date(lesson.date)}")
    if "duration" in include_fields:
        lines.append(f"- **{labels['duration_field']}:** {_format_duration(lesson.duration)}")
    if "course_name" in include_fields:
        lines.append(f"- **{labels['course_field']}:** {lesson.course.name if lesson.course else '-'}")
    if "themes" in include_fields:
        lines.append(f"- **{labels['themes_field']}:**  {_lesson_themes(session, lesson)}")
    if "brief" in include_fields:
        lines.append(f"- **{labels['themes_field']}:**\n")
        lines.append(f"  {(lesson.brief or '-').strip() or '-'}")
    lines.append("---")
    return lines


def _build_transcript_markdown(transcript: Any, *, labels: Dict[str, str]) -> str:
    rows = transcript if isinstance(transcript, list) else []
    if not rows:
        return labels["no_transcript"]
    lines: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        start = row.get("start")
        end = row.get("end")
        if start is not None and end is not None:
            lines.append(f"- [{_format_duration(float(start))} - {_format_duration(float(end))}] {text}")
        else:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else labels["no_transcript"]


def _build_sources_markdown(lesson: Lesson, session: Session, *, detailed: bool, labels: Dict[str, str]) -> str:
    sources = crud.get_lesson_sources(session, lesson.id)
    if not sources:
        return labels["no_sources"]

    grouped: Dict[str, List[Any]] = defaultdict(list)
    for source in sources:
        grouped[source.type or labels["unknown_source_type"]].append(source)

    lines: List[str] = []
    for source_type in sorted(grouped.keys()):
        lines.append(f"## {source_type}")
        lines.append("")
        for source in grouped[source_type]:
            citation = ", ".join(
                part
                for part in [source.work, source.ref, f"({source.standard_slug})" if source.standard_slug else None]
                if part
            )
            text = source.translation_text or source.original_text or ""
            brief = text[:180] + ("..." if len(text) > 180 else "")
            lines.append(f"- **{citation or labels['source_word']}**")
            if brief:
                lines.append(f"  - {brief}")
            if detailed:
                lines.append(f"  - paragraph_index: {source.paragraph_index}")
                lines.append(f"  - confidence: {source.confidence if source.confidence is not None else '-'}")
                lines.append(f"  - slug_retrieved: {source.slug_retrieved}")
                lines.append(f"  - verification_status: {source.verification_status or '-'}")
                lines.append(
                    f"  - verification_confidence: {source.verification_confidence if source.verification_confidence is not None else '-'}"
                )
                if source.verification_explanation:
                    lines.append(f"  - verification_explanation: {source.verification_explanation}")
                if source.matched_text:
                    lines.append(f"  - matched_text: {source.matched_text}")
        lines.append("")
    return "\n".join(lines).strip() or labels["no_sources"]


def build_lesson_markdown_export(
    *,
    session: Session,
    lesson: Lesson,
    export_type: LessonExportType,
    include_fields: Optional[Sequence[str]] = None,
    transcript_type: Literal["corrected", "initial"] = "corrected",
    language: Optional[str] = None,
) -> Tuple[str, str]:
    labels = _I18N_LABELS[_normalize_language(language)]
    selected_fields = _sanitize_lesson_fields(include_fields)
    preface = _render_lesson_metadata(
        session,
        lesson,
        selected_fields,
        labels=labels,
    )

    if export_type == "summary":
        content = (lesson.summary or "").strip()
        if not content:
            raise HTTPException(status_code=404, detail="No summary available")
        title = labels["summary_title"]
        suffix = "summary"
    elif export_type == "edited":
        content = edited_transcript_markdown(lesson.edited_transcript).strip()
        if not content:
            raise HTTPException(status_code=404, detail="No edited transcript available")
        title = labels["edited_title"]
        suffix = "edited_version"
    elif export_type == "transcript":
        transcript = lesson.corrected_transcript if transcript_type == "corrected" else lesson.transcript
        if not transcript:
            raise HTTPException(status_code=404, detail=f"No {transcript_type} transcript available")
        content = _build_transcript_markdown(transcript, labels=labels)
        transcript_variant = labels["corrected"] if transcript_type == "corrected" else labels["initial"]
        title = f"{labels['transcript_title']} ({transcript_variant})"
        suffix = f"{transcript_type}_transcript"
    elif export_type == "sources":
        content = _build_sources_markdown(lesson, session, detailed=False, labels=labels)
        title = labels["sources_title"]
        suffix = "sources"
    elif export_type == "sources_detailed":
        content = _build_sources_markdown(lesson, session, detailed=True, labels=labels)
        title = labels["sources_detailed_title"]
        suffix = "sources_detailed"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported lesson export type: {export_type}")

    # lines: List[str] = [f"# {title}", ""]
    lines: List[str] = []
    if preface:
        lines.extend(preface)
        lines.extend(["", "---", ""])
    lines.append(content)
    markdown = "\n".join(lines).strip() + "\n"
    base_name = f"{_safe_filename(lesson.title, 'lesson')}_{suffix}"
    return markdown, base_name


def _get_booklet_or_404(session: Session, booklet_id: int) -> Booklet:
    booklet = session.get(Booklet, booklet_id)
    if booklet is None:
        raise HTTPException(status_code=404, detail="Booklet not found")
    return booklet


def _sorted_booklet_items(session: Session, booklet_id: int) -> List[BookletItem]:
    statement = (
        select(BookletItem)
        .where(BookletItem.booklet_id == booklet_id)
        .order_by(BookletItem.position, BookletItem.id)
    )
    return list(session.exec(statement).all())


def _booklet_lessons_context(session: Session, items: Sequence[BookletItem]) -> Tuple[Dict[int, Lesson], Dict[int, str], Dict[int, str]]:
    lesson_ids = [item.lesson_id for item in items if item.item_type == BookletItemType.LESSON and item.lesson_id]
    lessons: Dict[int, Lesson] = {}
    if lesson_ids:
        lesson_rows = list(session.exec(select(Lesson).where(Lesson.id.in_(lesson_ids))).all())
        lessons = {lesson.id: lesson for lesson in lesson_rows}

    course_ids = {lesson.course_id for lesson in lessons.values() if lesson.course_id is not None}
    course_names: Dict[int, str] = {}
    if course_ids:
        course_rows = list(session.exec(select(Course).where(Course.id.in_(course_ids))).all())
        course_names = {course.id: course.name for course in course_rows}

    theme_ids = {theme_id for lesson in lessons.values() for theme_id in lesson.get_themes()}
    theme_names: Dict[int, str] = {}
    if theme_ids:
        theme_rows = list(session.exec(select(Theme).where(Theme.id.in_(theme_ids))).all())
        theme_names = {theme.id: theme.name for theme in theme_rows}

    return lessons, course_names, theme_names


def build_booklet_markdown_export(
    *,
    session: Session,
    booklet_id: int,
    include_table_of_contents: bool = True,
    lesson_fields: Optional[Sequence[str]] = None,
    language: Optional[str] = None,
) -> Tuple[str, str]:
    labels = _I18N_LABELS[_normalize_language(language)]
    booklet = _get_booklet_or_404(session, booklet_id)
    fields = _sanitize_booklet_lesson_fields(lesson_fields)
    items = _sorted_booklet_items(session, booklet_id)
    lessons, course_names, theme_names = _booklet_lessons_context(session, items)

    lines: List[str] = [f"# {booklet.title}"]
    if booklet.subtitle:
        lines.extend(["", f"## {booklet.subtitle}"])
    if booklet.description:
        lines.extend(["", str(booklet.description).strip()])

    if include_table_of_contents:
        lines.extend(["", f"## {labels['table_of_contents']}", ""])
        for item in items:
            if not item.is_included:
                continue
            if item.item_type == BookletItemType.CHAPTER:
                lines.append(f"- **{item.chapter_title or labels['chapter_word']}**")
            elif item.lesson_id:
                lesson = lessons.get(item.lesson_id)
                lesson_title = item.custom_title or (lesson.title if lesson else f"{labels['lesson_word']} #{item.lesson_id}")
                lines.append(f"- {lesson_title}")

    for item in items:
        if not item.is_included:
            continue
        lines.extend(["", "---", ""])
        if item.item_type == BookletItemType.CHAPTER:
            lines.append(f"## {item.chapter_title or labels['chapter_word']}")
            if item.chapter_subtitle:
                lines.extend(["", f"### {item.chapter_subtitle}"])
            if item.chapter_body:
                lines.extend(["", str(item.chapter_body).strip()])
            continue

        if not item.lesson_id:
            lines.append(labels["lesson_item_missing"])
            continue

        lesson = lessons.get(item.lesson_id)
        if lesson is None:
            lines.append(labels["lesson_not_found"].format(lesson_id=item.lesson_id))
            continue

        lesson_title = item.custom_title or lesson.title
        lines.append(f"## {lesson_title}")
        if item.custom_intro:
            lines.extend(["", str(item.custom_intro).strip()])

        for field in fields:
            if field == "date":
                lines.extend(["", f"- **{labels['date_field']}:** {_format_date(lesson.date)}"])
            elif field == "duration":
                lines.extend(["", f"- **{labels['duration_field']}:** {_format_duration(lesson.duration)}"])
            elif field == "course_name":
                course = course_names.get(lesson.course_id) if lesson.course_id is not None else None
                lines.extend(["", f"- **{labels['course_field']}:** {course or '-'}"])
            elif field == "themes":
                lesson_theme_names = [theme_names[theme_id] for theme_id in lesson.get_themes() if theme_id in theme_names]
                lines.extend(["", f"- **{labels['themes_field']}:** {', '.join(lesson_theme_names) if lesson_theme_names else '-'}"])
            elif field == "brief":
                lines.extend(["", f"### {labels['brief_field']}", "", (lesson.brief or "-").strip() or "-"])
            elif field == "summary":
                lines.extend(["", f"### {labels['summary_heading']}", "", (lesson.summary or "-").strip() or "-"])
            elif field == "edited_version":
                edited = edited_transcript_markdown(lesson.edited_transcript).strip()
                lines.extend(["", f"### {labels['edited_heading']}", "", edited or "-"])

    markdown = "\n".join(lines).strip() + "\n"
    base_name = _safe_filename(booklet.title, "booklet")
    return markdown, base_name


def _cloudconvert_docx_to_pdf(docx_bytes: bytes, filename: str) -> bytes:
    api_key = os.getenv("CLOUDCONVERT_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="CLOUDCONVERT_API_KEY is not configured")

    encoded = base64.b64encode(docx_bytes).decode("ascii")
    headers = {"Authorization": f"Bearer {api_key}"}
    tasks = {
        "import-docx": {
            "operation": "import/base64",
            "file": encoded,
            "filename": filename,
        },
        "convert-pdf": {
            "operation": "convert",
            "input": "import-docx",
            "output_format": "pdf",
        },
        "export-pdf": {
            "operation": "export/url",
            "input": "convert-pdf",
            "inline": False,
            "archive_multiple_files": False,
        },
    }

    with httpx.Client(timeout=60.0) as client:
        create_resp = client.post(
            "https://api.cloudconvert.com/v2/jobs",
            headers=headers,
            json={"tasks": tasks},
        )
        create_resp.raise_for_status()
        create_payload = create_resp.json().get("data") or {}
        job_id = create_payload.get("id")
        if not job_id:
            raise HTTPException(status_code=502, detail="CloudConvert did not return a job id")

        # Wait for completion with small retries to avoid long-hanging request chains.
        wait_url = f"https://sync.api.cloudconvert.com/v2/jobs/{job_id}"
        final_payload: Dict[str, Any] = {}
        for _ in range(8):
            wait_resp = client.get(wait_url, headers=headers)
            if wait_resp.status_code >= 500:
                time.sleep(1.5)
                continue
            wait_resp.raise_for_status()
            final_payload = (wait_resp.json() or {}).get("data") or {}
            status = final_payload.get("status")
            if status == "finished":
                break
            if status == "error":
                message = final_payload.get("message") or "CloudConvert conversion failed"
                raise HTTPException(status_code=502, detail=message)
            time.sleep(1.5)

        tasks_payload = final_payload.get("tasks") or []
        export_task = next((task for task in tasks_payload if task.get("name") == "export-pdf"), None)
        files = (export_task or {}).get("result", {}).get("files") or []
        if not files or not files[0].get("url"):
            raise HTTPException(status_code=502, detail="CloudConvert did not return an exported PDF file")
        pdf_url = files[0]["url"]
        pdf_resp = client.get(pdf_url)
        pdf_resp.raise_for_status()
        return pdf_resp.content


def render_markdown_to_format(markdown: str, base_filename: str, export_format: ExportFormat) -> Tuple[bytes, str, str]:
    format_value = str(export_format).lower()
    if format_value == "md":
        return markdown.encode("utf-8"), f"{base_filename}.md", _MD_MIME
    if format_value == "docx":
        docx_bytes = markdown_to_docx_bytes(markdown)
        return docx_bytes, f"{base_filename}.docx", _DOCX_MIME
    if format_value == "pdf":
        docx_bytes = markdown_to_docx_bytes(markdown)
        pdf_bytes = _cloudconvert_docx_to_pdf(docx_bytes, f"{base_filename}.docx")
        return pdf_bytes, f"{base_filename}.pdf", _PDF_MIME
    raise HTTPException(status_code=400, detail=f"Unsupported export format: {export_format}")


def generate_lesson_export(
    *,
    session: Session,
    lesson: Lesson,
    export_type: LessonExportType,
    export_format: ExportFormat,
    include_fields: Optional[Sequence[str]] = None,
    transcript_type: Literal["corrected", "initial"] = "corrected",
    language: Optional[str] = None,
) -> Tuple[bytes, str, str]:
    markdown, base_filename = build_lesson_markdown_export(
        session=session,
        lesson=lesson,
        export_type=export_type,
        include_fields=include_fields,
        transcript_type=transcript_type,
        language=language,
    )
    return render_markdown_to_format(markdown, base_filename, export_format)


def generate_booklet_export(
    *,
    session: Session,
    booklet_id: int,
    export_format: ExportFormat,
    include_table_of_contents: bool = True,
    lesson_fields: Optional[Sequence[str]] = None,
    language: Optional[str] = None,
) -> Tuple[bytes, str, str]:
    markdown, base_filename = build_booklet_markdown_export(
        session=session,
        booklet_id=booklet_id,
        include_table_of_contents=include_table_of_contents,
        lesson_fields=lesson_fields,
        language=language,
    )
    return render_markdown_to_format(markdown, base_filename, export_format)

