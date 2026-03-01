"""PDF generation service — wraps pdf_reportlab calls with filename building."""

from typing import List
from sqlmodel import Session
from models import Lesson
import crud


def _safe_filename(title: str) -> str:
    """Strip characters unsafe for filenames from a lesson title."""
    return "".join(
        c for c in title if c.isalnum() or c in (" ", "-", "_")
    ).rstrip()


def _edited_with_sources(lesson: Lesson, session: Session) -> List[dict]:
    """Return edited_transcript dicts with sources merged in from the lesson_source table."""
    parts = []
    if not lesson.edited_transcript:
        return parts

    db_sources = crud.get_lesson_sources(session, lesson.id)
    # Group DB sources by paragraph_index
    sources_by_para: dict[int, list] = {}
    for s in db_sources:
        sources_by_para.setdefault(s.paragraph_index, []).append({
            "type": s.type,
            "work": s.work,
            "ref": s.ref,
            "standard_slug": s.standard_slug,
            "original_text": s.original_text,
            "translation_text": s.translation_text,
            "cited_excerpt": s.cited_excerpt,
            "confidence": s.confidence,
            "slug_retrieved": s.slug_retrieved,
            "verification_status": s.verification_status,
            "verification_confidence": s.verification_confidence,
            "verification_explanation": s.verification_explanation,
            "matched_text": s.matched_text,
        })

    for idx, part in enumerate(lesson.edited_transcript):
        if isinstance(part, dict):
            p = part.copy()
        else:
            p = part.model_dump() if hasattr(part, "model_dump") else dict(part)
        p["sources"] = sources_by_para.get(idx, [])
        parts.append(p)

    return parts


def generate_summary_pdf(lesson: Lesson) -> tuple[bytes, str]:
    """Generate a summary PDF. Returns (pdf_bytes, attachment_filename)."""
    from pdf_reportlab import generate_lesson_summary_pdf

    prompt_name = None
    if lesson.summary_metadata:
        prompt_text = lesson.summary_metadata.get("prompt", "")
        if prompt_text.startswith("["):
            end_bracket = prompt_text.find("]")
            if end_bracket > 0:
                prompt_name = prompt_text[1:end_bracket]

    pdf_bytes = generate_lesson_summary_pdf(
        title=lesson.title,
        summary_markdown=lesson.summary,
        brief_text=lesson.brief,
        filename=lesson.filename,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
        prompt_name=prompt_name,
        summary_metadata=lesson.summary_metadata,
    )
    return pdf_bytes, f"{_safe_filename(lesson.title)}_summary.pdf"


def generate_transcript_pdf(lesson: Lesson, transcript_type: str) -> tuple[bytes, str]:
    """Generate a transcript PDF. Returns (pdf_bytes, attachment_filename)."""
    from pdf_reportlab import generate_lesson_transcript_pdf

    transcript = (
        lesson.corrected_transcript
        if transcript_type == "corrected"
        else lesson.transcript
    )
    pdf_bytes = generate_lesson_transcript_pdf(
        title=lesson.title,
        transcript=transcript,
        filename=lesson.filename,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
        transcript_type=transcript_type,
    )
    return pdf_bytes, f"{_safe_filename(lesson.title)}_{transcript_type}_transcript.pdf"


def generate_edited_pdf(lesson: Lesson, session: Session) -> tuple[bytes, str]:
    """Generate an edited transcript PDF. Returns (pdf_bytes, attachment_filename)."""
    from pdf_reportlab import generate_lesson_edited_transcript_pdf

    pdf_bytes = generate_lesson_edited_transcript_pdf(
        title=lesson.title,
        edited_transcript=_edited_with_sources(lesson, session),
        filename=lesson.filename,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
    )
    return pdf_bytes, f"{_safe_filename(lesson.title)}_edited.pdf"


def generate_sources_pdf(lesson: Lesson, session: Session) -> tuple[bytes, str]:
    """Generate a sources PDF grouped by author. Returns (pdf_bytes, attachment_filename)."""
    from pdf_reportlab import generate_lesson_sources_pdf

    pdf_bytes = generate_lesson_sources_pdf(
        title=lesson.title,
        edited_transcript=_edited_with_sources(lesson, session),
        filename=lesson.filename,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
    )
    return pdf_bytes, f"{_safe_filename(lesson.title)}_sources.pdf"


def generate_detailed_sources_pdf(lesson: Lesson, session: Session) -> tuple[bytes, str]:
    """Generate a detailed sources PDF with full information. Returns (pdf_bytes, attachment_filename)."""
    from pdf_reportlab import generate_lesson_detailed_sources_pdf

    pdf_bytes = generate_lesson_detailed_sources_pdf(
        title=lesson.title,
        edited_transcript=_edited_with_sources(lesson, session),
        filename=lesson.filename,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
    )
    return pdf_bytes, f"{_safe_filename(lesson.title)}_sources_detailed.pdf"
