"""Common Pydantic schemas for LLM processing metadata."""

from pydantic import BaseModel
from typing import Optional


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
