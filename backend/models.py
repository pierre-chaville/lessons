"""SQLModel database models"""

from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import json


class Segment(BaseModel):
    """Transcript segment with timing and text"""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Transcript text


class Source(BaseModel):
    """Source used in a lesson, a portion of text from another author"""

    author: str  # Author name (e.g. Cicero)
    work: str  # Work name (e.g. De Officiis)
    reference: str  # Reference (e.g. Book I, Section 2)
    text: str  # Source text
    cited_excerpt: Optional[str] = (
        None  # The excerpt from edited text that cites this source
    )


class EditedPart(BaseModel):
    """Edited part of the transcript"""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    text: str  # Original text
    sources: List[Source]  # List of sources used in this part


class Metadata(BaseModel):
    """Metadata for LLM processing (correction/summary)"""

    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
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


class Course(SQLModel, table=True):
    """Course model"""

    __tablename__ = "course"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None

    # Relationships
    lessons: List["Lesson"] = Relationship(back_populates="course")


class Theme(SQLModel, table=True):
    """Theme model"""

    __tablename__ = "theme"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class Lesson(SQLModel, table=True):
    """Lesson model"""

    __tablename__ = "lesson"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    date: datetime = Field(default_factory=datetime.now)
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")
    filename: str  # Audio filename
    duration: Optional[float] = None  # Duration in seconds
    transcript: Optional[List[Segment]] = Field(
        default=None, sa_column=Column(JSON)
    )  # List of segments
    corrected_transcript: Optional[List[Segment]] = Field(
        default=None, sa_column=Column(JSON)
    )  # List of segments
    edited_transcript: Optional[List[EditedPart]] = Field(
        default=None, sa_column=Column(JSON)
    )  # List of edited parts with sources
    brief: Optional[str] = None  # Short 1-3 line summary
    summary: Optional[str] = None

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


class Task(SQLModel, table=True):
    """Background task tracking"""

    __tablename__ = "task"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    task_type: str  # Type of task (e.g., "transcription", "correction", "summary")
    status: str = Field(default="pending")  # pending, running, completed, failed
    start_date: Optional[datetime] = None  # When task started
    end_date: Optional[datetime] = None  # When task completed/failed
    duration: Optional[float] = None  # Duration in seconds
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Task parameters
    result: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Task result
    error: Optional[str] = None  # Error message if failed
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )  # When task was created
