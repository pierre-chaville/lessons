"""Pydantic schemas for course API requests."""

from pydantic import BaseModel
from typing import Optional


class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
