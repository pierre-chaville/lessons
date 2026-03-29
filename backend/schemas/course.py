"""Pydantic schemas for course API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class CourseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CourseResponse(BaseModel):
    """Flat course response with hashid and parent reference."""

    id: int
    hashid: str = ""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class CourseTreeNode(BaseModel):
    """Recursive tree node for hierarchical course display."""

    id: int
    hashid: str = ""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    lesson_count: int = 0
    children: List[CourseTreeNode] = []

    class Config:
        from_attributes = True
