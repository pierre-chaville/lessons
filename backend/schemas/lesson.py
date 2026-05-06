"""Pydantic schemas for lessons and versioning APIs."""

from enum import Enum

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from schemas.source import Source, LessonSourceResponse
from schemas.theme import ThemeResponse
from schemas.course import CourseResponse
from hashid_utils import encode_id


class ContentType(str, Enum):
    TITLE = "title"
    CORRECTED_TRANSCRIPT = "corrected_transcript"
    EDITED_TRANSCRIPT = "edited_transcript"
    BRIEF = "brief"
    SUMMARY = "summary"


class VersionSource(str, Enum):
    HUMAN = "human"
    PIPELINE = "pipeline"
    RESTORE = "restore"


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
    editor_ids: Optional[List[str]] = None


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
    process_status: Optional[str] = None
    theme_ids: Optional[List[int]] = None
    editor_ids: Optional[List[str]] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None


VALID_STATUSES = {"draft", "in_progress", "review_requested", "revision_requested", "validated"}

ALLOWED_TRANSITIONS: Dict[str, Dict[str, list]] = {
    "draft":               {"in_progress":       ["editor", "publisher", "admin"]},
    "in_progress":         {"review_requested":   ["editor", "publisher", "admin"]},
    "review_requested":    {"validated":          ["publisher", "admin"],
                            "revision_requested": ["publisher", "admin"]},
    "revision_requested":  {"in_progress":        ["editor", "publisher", "admin"]},
    "validated":           {"in_progress":        ["admin"]},
}


class StatusUpdate(BaseModel):
    """Schema for changing lesson workflow status"""
    status: str
    reason: Optional[str] = None


class RestoreVersionRequest(BaseModel):
    reason: Optional[str] = None


class CheckpointRequest(BaseModel):
    content_type: ContentType
    reason: Optional[str] = None


class VersionResponse(BaseModel):
    id: UUID
    lesson_id: int
    content_type: ContentType
    version_number: int
    version_source: VersionSource
    created_at: datetime
    last_edited_at: Optional[datetime]
    edit_count: int
    is_sealed: bool
    sealed_at: Optional[datetime]
    sealed_reason: Optional[str]
    created_by_id: Optional[str]
    change_summary: Optional[str]
    parent_version_id: Optional[UUID]
    restored_from_id: Optional[UUID]
    is_current: bool
    content: Optional[Any] = None

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: int
    occurred_at: datetime
    actor_id: Optional[str]
    actor_role: str
    entity_type: str
    entity_id: str
    action: str
    payload: Dict[str, Any]

    class Config:
        from_attributes = True


class LessonEditorResponse(BaseModel):
    """Editor assignment for a lesson."""
    user_id: str
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        from_attributes = True


class LessonListResponse(BaseModel):
    """Lightweight lesson response for list view"""

    id: int
    hashid: str = ""
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    status: str = "draft"
    process_status: Optional[str] = None
    filename: str
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None
    editors: List[LessonEditorResponse] = []

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
    status: str = "draft"
    process_status: Optional[str] = None
    theme_ids: List[int]
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None
    sources: List[LessonSourceResponse] = []
    editors: List[LessonEditorResponse] = []
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
