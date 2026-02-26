"""Pydantic schemas for course API requests and responses."""

from pydantic import BaseModel
from typing import Optional


class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CourseResponse(BaseModel):
    """Course response with hashid."""

    id: int
    hashid: str = ""
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
