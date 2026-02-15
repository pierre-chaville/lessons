"""Pydantic schemas for search API responses."""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from models.theme import Theme
from models.course import Course


class SearchMatchSegment(BaseModel):
    start: float
    end: float
    text: str
    score: float
    exact: bool


class SearchLessonResult(BaseModel):
    id: int
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    filename: str
    themes: List[Theme] = []
    course: Optional[Course] = None
    matches: List[SearchMatchSegment]
    match_count: int
    best_score: float

    class Config:
        from_attributes = True
