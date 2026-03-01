"""Pydantic schemas for Torah sources referenced in lessons."""

from pydantic import BaseModel
from typing import Optional


class Source(BaseModel):
    """Source used in a lesson, a portion of text from another author.
    
    This schema is used both as an internal data structure during extraction /
    verification and as the API response shape for individual sources.
    """

    type: Optional[str] = None  # Type of source (e.g., Torah, Mishnah, Gemara, Midrash, etc.)
    work: Optional[str] = None  # Work title (e.g., Pirkei Avot)
    ref: Optional[str] = None  # Reference to the source (e.g., 4.2)
    standard_slug: Optional[str] = None  # Standard slug in Sefaria for the source (e.g., Pirkei_Avot.4.2)
    original_text: Optional[str] = None  # Source text in the original language
    translation_text: Optional[str] = None  # Source text in the lesson language (fr)
    cited_excerpt: Optional[str] = None  # The excerpt from edited text that cites this source
    confidence: Optional[float] = None  # Confidence score between 0 and 1
    # Source verification fields
    slug_retrieved: Optional[bool] = None  # Whether the API successfully retrieved the slug
    verification_status: Optional[str] = None  # exactly_found, paraphrase_or_similar, partially_found, not_found, or reference_exists_but_text_differs
    verification_confidence: Optional[float] = None  # Confidence score from verification (0-1)
    verification_explanation: Optional[str] = None  # Explanation of the verification result
    matched_text: Optional[str] = None  # The matched text found in the source


class LessonSourceResponse(BaseModel):
    """API response for a source linked to a lesson (from lesson_source table)."""

    id: int
    lesson_id: int
    paragraph_index: int
    type: Optional[str] = None
    work: Optional[str] = None
    ref: Optional[str] = None
    standard_slug: Optional[str] = None
    original_text: Optional[str] = None
    translation_text: Optional[str] = None
    cited_excerpt: Optional[str] = None
    confidence: Optional[float] = None
    slug_retrieved: Optional[bool] = None
    verification_status: Optional[str] = None
    verification_confidence: Optional[float] = None
    verification_explanation: Optional[str] = None
    matched_text: Optional[str] = None

    class Config:
        from_attributes = True
