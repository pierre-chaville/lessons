"""Pydantic schemas for theme API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class ThemeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class ThemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class ThemeResponse(BaseModel):
    """Flat theme response with hashid and parent reference."""

    id: int
    hashid: str = ""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0

    class Config:
        from_attributes = True


class ThemeTreeNode(BaseModel):
    """Recursive tree node for hierarchical theme display."""

    id: int
    hashid: str = ""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    lesson_count: int = 0
    children: List[ThemeTreeNode] = []

    class Config:
        from_attributes = True
