"""SQLModel table model for lessons."""

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from models.course import Course
from schemas.common import Metadata, TranscriptMetadata
from schemas.lesson import Segment, EditedParagraph


class Lesson(SQLModel, table=True):
    """Lesson model"""

    __tablename__ = "lesson"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str  # Editable field stored directly on lesson (not versioned).
    date: datetime = Field(default_factory=datetime.now)
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")
    filename: str  # Audio filename
    duration: Optional[float] = None  # Duration in seconds
    transcript: Optional[List[Segment]] = Field(
        default=None, sa_column=Column(JSON)
    )  # List of segments
    corrected_transcript: Optional[List[Segment]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Mirrored from current ContentVersion. Do not write directly. Use services.versioning.update_content.
    edited_transcript: Optional[List[EditedParagraph]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Mirrored from current ContentVersion. Do not write directly. Use services.versioning.update_content.
    brief: Optional[str] = None  # Mirrored from current ContentVersion. Do not write directly. Use services.versioning.update_content.
    summary: Optional[str] = None  # Mirrored from current ContentVersion. Do not write directly. Use services.versioning.update_content.
    status: str = Field(default="draft")  # Workflow status: draft, in_progress, review_requested, revision_requested, validated
    process_status: Optional[str] = None  # Current processing step: transcript, edition, sources_extraction, sources_checking, summary

    # Metadata for transcript, correction, summary and edited transcript
    transcript_metadata: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )
    correction_metadata: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )
    summary_metadata: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )
    edited_metadata: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )

    # JSON field for themes (stored as JSON array of theme IDs)
    themes_json: Optional[str] = Field(default=None)

    # Relationships
    course: Optional[Course] = Relationship(back_populates="lessons")

    def get_themes(self) -> List[int]:
        """Get themes as list of IDs"""
        if self.themes_json:
            try:
                return json.loads(self.themes_json)
            except json.JSONDecodeError:
                return []
        return []

    def set_themes(self, theme_ids: List[int]):
        """Set themes from list of IDs"""
        self.themes_json = json.dumps(theme_ids) if theme_ids else None

    def get_transcript_metadata(self) -> Optional[TranscriptMetadata]:
        """Get transcript metadata as TranscriptMetadata object"""
        if self.transcript_metadata:
            return TranscriptMetadata(**self.transcript_metadata)
        return None

    def set_transcript_metadata(self, metadata: TranscriptMetadata):
        """Set transcript metadata from TranscriptMetadata object"""
        self.transcript_metadata = metadata.model_dump() if metadata else None

    def get_correction_metadata(self) -> Optional[Metadata]:
        """Get correction metadata as Metadata object"""
        if self.correction_metadata:
            return Metadata(**self.correction_metadata)
        return None

    def set_correction_metadata(self, metadata: Metadata):
        """Set correction metadata from Metadata object"""
        self.correction_metadata = metadata.model_dump() if metadata else None

    def get_summary_metadata(self) -> Optional[Metadata]:
        """Get summary metadata as Metadata object"""
        if self.summary_metadata:
            return Metadata(**self.summary_metadata)
        return None

    def set_summary_metadata(self, metadata: Metadata):
        """Set summary metadata from Metadata object"""
        self.summary_metadata = metadata.model_dump() if metadata else None

    def get_edited_metadata(self) -> Optional[Metadata]:
        """Get edited transcript metadata as Metadata object"""
        if self.edited_metadata:
            return Metadata(**self.edited_metadata)
        return None

    def set_edited_metadata(self, metadata: Metadata):
        """Set edited transcript metadata from Metadata object"""
        self.edited_metadata = metadata.model_dump() if metadata else None
