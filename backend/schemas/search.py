"""Pydantic schemas for search API responses."""

from pydantic import BaseModel
from typing import List, Optional
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
