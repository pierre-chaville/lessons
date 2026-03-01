"""Pydantic schemas for lesson transcript segments, paragraphs, and API request/response models."""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from schemas.source import Source, LessonSourceResponse
from schemas.theme import ThemeResponse
from schemas.course import CourseResponse
from hashid_utils import encode_id


class Segment(BaseModel):
    """Transcript segment with timing and text"""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Transcript text


class EditedParagraph(BaseModel):
    """Edited paragraph of the transcript"""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Original text
    sources: List[Source] = []  # kept for backward compat with JSON storage during edition


class LessonCreate(BaseModel):
    """Schema for creating a lesson"""

    title: str
    filename: str
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    duration: Optional[float] = None
    transcript: Optional[Dict[str, Any]] = None
    corrected_transcript: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    theme_ids: Optional[List[int]] = None


class LessonUpdate(BaseModel):
    """Schema for updating a lesson"""

    title: Optional[str] = None
    filename: Optional[str] = None
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    duration: Optional[float] = None
    transcript: Optional[List[Segment]] = None
    corrected_transcript: Optional[List[Segment]] = None
    edited_transcript: Optional[List[EditedParagraph]] = None
    brief: Optional[str] = None
    summary: Optional[str] = None
    process_status: Optional[str] = None  # transcript, edition, sources_extraction, sources_checking, summary
    theme_ids: Optional[List[int]] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None


class LessonListResponse(BaseModel):
    """Lightweight lesson response for list view"""

    id: int
    hashid: str = ""
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    process_status: Optional[str] = None
    filename: str
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None

    class Config:
        from_attributes = True


class LessonResponse(BaseModel):
    """Full lesson response with all fields and enriched relations"""

    id: int
    hashid: str = ""
    title: str
    filename: str
    course_id: Optional[int]
    date: datetime
    duration: Optional[float]
    transcript: Optional[List[Segment]]
    corrected_transcript: Optional[List[Segment]]
    edited_transcript: Optional[List[EditedParagraph]]
    brief: Optional[str]
    summary: Optional[str]
    process_status: Optional[str] = None
    theme_ids: List[int]
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None
    sources: List[LessonSourceResponse] = []
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
