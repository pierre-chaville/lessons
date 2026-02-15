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
    """Metadata for Whisper transcription"""

    model_size: Optional[str] = None
    device: Optional[str] = None
    compute_type: Optional[str] = None
    beam_size: Optional[int] = None
    vad_filter: Optional[bool] = None
    language: Optional[str] = None
    initial_prompt: Optional[str] = None
