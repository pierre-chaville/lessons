"""Pydantic schemas for theme API requests and responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional


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


# ── JSON export / import ──────────────────────────────────────────────────────
# Themes are transferred as a name-based tree (no ids) so a file exported from
# one environment can be imported into another, or written by hand.


class ThemeTransferNode(BaseModel):
    """One theme in an export/import file; children are nested."""

    name: str
    description: Optional[str] = None
    children: List[ThemeTransferNode] = []

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Theme name must not be empty")
        return value


class ThemeExport(BaseModel):
    format: Literal["themes"] = "themes"
    version: int = 1
    exported_at: datetime
    themes: List[ThemeTransferNode]


class ThemeImportRequest(BaseModel):
    """Accepts an export file as-is: extra keys (format, version, exported_at) are ignored."""

    themes: List[ThemeTransferNode]


class ThemeImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    total: int
