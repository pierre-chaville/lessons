"""Pydantic schemas for Sefaria cache API."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SefariaCacheCreate(BaseModel):
    """Schema for creating a Sefaria cache entry."""
    type: Optional[str] = None
    work: Optional[str] = None
    ref: Optional[str] = None
    he_ref: Optional[str] = None
    standard_slug: str
    text_english: Optional[str] = None
    text_hebrew: Optional[str] = None


class SefariaCacheUpdate(BaseModel):
    """Schema for updating a Sefaria cache entry."""
    type: Optional[str] = None
    work: Optional[str] = None
    ref: Optional[str] = None
    he_ref: Optional[str] = None
    text_english: Optional[str] = None
    text_hebrew: Optional[str] = None


class SefariaCacheResponse(BaseModel):
    """Schema for returning a Sefaria cache entry."""
    id: int
    type: Optional[str] = None
    work: Optional[str] = None
    ref: Optional[str] = None
    he_ref: Optional[str] = None
    standard_slug: str
    text_english: Optional[str] = None
    text_hebrew: Optional[str] = None
    fetched_at: datetime
