"""Pydantic schemas for search API responses."""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

from schemas.theme import ThemeResponse
from schemas.course import CourseResponse


class SearchMatchSegment(BaseModel):
    start: float
    end: float
    text: str
    score: float
    exact: bool


class SearchLessonResult(BaseModel):
    id: int
    hashid: str = ""
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    filename: str
    themes: List[ThemeResponse] = []
    course: Optional[CourseResponse] = None
    matches: List[SearchMatchSegment]
    match_count: int
    best_score: float

    class Config:
        from_attributes = True


class RagSearchRequest(BaseModel):
    question: str = Field(..., min_length=1)
    lesson_ids: Optional[List[int]] = None
    variant: Literal["edited", "summary"] = "edited"


class RagSearchCitation(BaseModel):
    reference_number: int
    chunk_id: int
    lesson_id: int
    lesson_hashid: str = ""
    lesson_title: str
    lesson_course_path: Optional[str] = None
    lesson_date: datetime
    variant: Literal["edited", "summary"]
    chunk_index: int
    previous_paragraph: str = ""
    snippet: str
    score: float


class RagSearchResponse(BaseModel):
    answer: str
    citations: List[RagSearchCitation] = []
