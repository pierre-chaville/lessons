"""Pydantic request/response schemas (non-table models)."""

from schemas.common import Metadata, TranscriptMetadata
from schemas.source import Source
from schemas.lesson import Segment, EditedParagraph, LessonCreate, LessonUpdate, LessonListResponse, LessonResponse
from schemas.course import CourseCreate, CourseUpdate
from schemas.theme import ThemeCreate, ThemeUpdate
from schemas.task import TaskCreate, TaskResponse
from schemas.search import SearchMatchSegment, SearchLessonResult
from schemas.config import ConfigUpdate

__all__ = [
    "Metadata",
    "TranscriptMetadata",
    "Source",
    "Segment",
    "EditedParagraph",
    "LessonCreate",
    "LessonUpdate",
    "LessonListResponse",
    "LessonResponse",
    "CourseCreate",
    "CourseUpdate",
    "ThemeCreate",
    "ThemeUpdate",
    "TaskCreate",
    "TaskResponse",
    "SearchMatchSegment",
    "SearchLessonResult",
    "ConfigUpdate",
]
