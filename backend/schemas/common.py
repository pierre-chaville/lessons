"""Common Pydantic schemas for LLM processing metadata."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class Metadata(BaseModel):
    """Metadata for LLM processing (correction/summary)"""

    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    prompt: Optional[str] = None


class TranscriptMetadata(BaseModel):
    """Metadata for Deepgram transcription"""

    provider: Optional[str] = None
    model: Optional[str] = None
    language: Optional[str] = None


class HebrewMode(str, Enum):
    """How Hebrew terms are written in a text.

    - TRANSLIT: transliterated in Latin letters (e.g. "techouva")
    - NATIVE: Hebrew alphabet (e.g. "תְּשׁוּבָה")
    - PARTIAL: legacy transliterated text partially converted to native
    """

    TRANSLIT = "translit"
    NATIVE = "native"
    PARTIAL = "partial"


DEFAULT_HEBREW_MODE = HebrewMode.TRANSLIT


def parse_hebrew_mode(value: Any) -> HebrewMode:
    """Coerce a raw value (config, DB) to a HebrewMode, defaulting to translit."""
    if isinstance(value, HebrewMode):
        return value
    try:
        return HebrewMode(str(value))
    except ValueError:
        return DEFAULT_HEBREW_MODE
