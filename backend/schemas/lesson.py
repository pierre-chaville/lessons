"""Pydantic schemas for lessons and versioning APIs."""

from enum import Enum

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
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
    sources: List[Source] = Field(default_factory=list)  # kept for backward compat with legacy JSON payloads


class EditedAlignment(BaseModel):
    """Alignment row mapping one edited paragraph to transcript segments."""

    start: Optional[float] = None
    end: Optional[float] = None
    match_score: float = 0.0
    start_index: Optional[int] = None
    end_index: Optional[int] = None


class EditedTranscript(BaseModel):
    """Edited transcript payload stored in lesson/content_version JSON."""

    markdown: str
    sources: List[List[Source]] = Field(default_factory=list)
    alignment: List[EditedAlignment] = Field(default_factory=list)
    transcript_hash: Optional[str] = None
    markdown_hash: Optional[str] = None
    aligned_at: Optional[datetime] = None


class LessonCreate(BaseModel):
    """Schema for creating a lesson"""

    title: str
    filename: str
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    hebrew_year: Optional[str] = None
    duration: Optional[float] = None
    transcript: Optional[Dict[str, Any]] = None
    corrected_transcript: Optional[Dict[str, Any]] = None
    brief: Optional[str] = None
    summary: Optional[str] = None
    pdf_files: Optional[List[str]] = None
    legacy_url: Optional[str] = None
    theme_ids: Optional[List[int]] = None
    editor_ids: Optional[List[str]] = None


class LessonUpdate(BaseModel):
    """Schema for updating a lesson"""

    title: Optional[str] = None
    filename: Optional[str] = None
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    hebrew_year: Optional[str] = None
    duration: Optional[float] = None
    transcript: Optional[List[Segment]] = None
    corrected_transcript: Optional[List[Segment]] = None
    edited_transcript: Optional[EditedTranscript | List[EditedParagraph]] = None
    brief: Optional[str] = None
    summary: Optional[str] = None
    process_status: Optional[str] = None
    step_statuses: Optional[Dict[str, str]] = None
    theme_ids: Optional[List[int]] = None
    editor_ids: Optional[List[str]] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None
    pdf_files: Optional[List[str]] = None
    legacy_url: Optional[str] = None


VALID_STATUSES = {"draft", "in_progress", "review_requested", "revision_requested", "validated"}

WORKFLOW_STEP_KEYS: tuple[str, ...] = (
    "transcription",
    "edited",
    "sources",
    "summary",
    "brief",
)
WORKFLOW_STEP_STATUSES: tuple[str, ...] = (
    "non_started",
    "failed",
    "to_review",
    "in_progress",
    "completed",
    "validated",
)
USER_MUTABLE_WORKFLOW_STEP_STATUSES = {"in_progress", "completed", "validated"}
WORKER_MUTABLE_WORKFLOW_STEP_STATUSES = {"failed", "to_review"}

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


class StepStatusUpdate(BaseModel):
    """Schema for changing one workflow step status."""

    status: str


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
    restored_from_version_number: Optional[int] = None
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
    user_name: Optional[str] = None
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
    hebrew_year: Optional[str] = None
    hebrew_date: Optional[str] = None
    duration: Optional[float]
    brief: Optional[str]
    status: str = "draft"
    process_status: Optional[str] = None
    step_statuses: Dict[str, str] = Field(default_factory=dict)
    edition_done: bool = False
    sources_done: bool = False
    summary_done: bool = False
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
    hebrew_year: Optional[str] = None
    hebrew_date: Optional[str] = None
    duration: Optional[float]
    transcript: Optional[List[Segment]]
    corrected_transcript: Optional[List[Segment]]
    edited_transcript: Optional[EditedTranscript]
    brief: Optional[str]
    summary: Optional[str]
    status: str = "draft"
    process_status: Optional[str] = None
    step_statuses: Dict[str, str] = Field(default_factory=dict)
    theme_ids: List[int]
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None
    sources: List[LessonSourceResponse] = []
    editors: List[LessonEditorResponse] = []
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None
    pdf_files: List[str] = Field(default_factory=list)
    legacy_url: Optional[str] = None

    class Config:
        from_attributes = True


class LessonDocumentUrlResponse(BaseModel):
    """Presigned URL for a stored lesson PDF document."""

    url: str


class LegacyLessonImportResponse(BaseModel):
    """Result returned by the fixed-key legacy lesson import endpoint."""

    lesson: LessonResponse
    task_id: int


class LessonBulkCsvImportResponse(BaseModel):
    """Result summary for bulk lesson CSV import."""

    updated_count: int
    skipped_count: int
    error_count: int
    updated_ids: List[int] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
