"""SQLModel table model for lesson sources (citations)."""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class LessonSource(SQLModel, table=True):
    """A source citation linked to a specific lesson and paragraph."""

    __tablename__ = "lesson_source"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(index=True, foreign_key="lesson.id")
    paragraph_index: int  # 0-based index in edited_transcript

    # Source identification
    type: Optional[str] = None  # Torah, Mishnah, Gemara, Midrash, etc.
    work: Optional[str] = None  # Work title (e.g., Pirkei Avot)
    ref: Optional[str] = None  # Reference (e.g., 4.2)
    standard_slug: Optional[str] = Field(default=None, index=True)  # Sefaria slug

    # Source content
    original_text: Optional[str] = None  # Source text in the original language
    translation_text: Optional[str] = None  # Source text in the lesson language
    cited_excerpt: Optional[str] = None  # Excerpt from edited text citing this source

    # Extraction confidence
    confidence: Optional[float] = None  # LLM extraction confidence (0-1)

    # Verification fields (populated by sources verification task)
    slug_retrieved: Optional[bool] = None
    verification_status: Optional[str] = None  # exactly_found, paraphrase_or_similar, partially_found, not_found, reference_exists_but_text_differs
    verification_confidence: Optional[float] = None
    verification_explanation: Optional[str] = None
    matched_text: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
