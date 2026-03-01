"""Pydantic request/response schemas (non-table models)."""

from schemas.common import Metadata, TranscriptMetadata
from schemas.source import Source, LessonSourceResponse
from schemas.lesson import Segment, EditedParagraph, LessonCreate, LessonUpdate, LessonListResponse, LessonResponse
from schemas.course import CourseCreate, CourseUpdate
from schemas.theme import ThemeCreate, ThemeUpdate
from schemas.task import TaskCreate, TaskResponse
from schemas.search import SearchMatchSegment, SearchLessonResult
from schemas.config import ConfigUpdate
from schemas.sefaria_cache import SefariaCacheCreate, SefariaCacheUpdate, SefariaCacheResponse

__all__ = [
    "Metadata",
    "TranscriptMetadata",
    "Source",
    "LessonSourceResponse",
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
    "SefariaCacheCreate",
    "SefariaCacheUpdate",
    "SefariaCacheResponse",
]
