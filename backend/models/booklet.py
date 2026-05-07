"""Booklet and generation models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _jsonb_column(default_factory: Callable[[], Any] = dict) -> Column:
    """Use JSONB on PostgreSQL and JSON elsewhere (tests/dev sqlite)."""
    return Column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=default_factory,
    )


class BookletStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class GenerationFormat(str, Enum):
    PDF = "pdf"
    HTML = "html"
    DOCX = "docx"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BookletItemType(str, Enum):
    LESSON = "lesson"
    CHAPTER = "chapter"


class Booklet(SQLModel, table=True):
    """A booklet is an ordered, customizable collection of lessons."""

    __tablename__ = "booklet"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(sa_column=Column(String, nullable=False))
    subtitle: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    status: BookletStatus = Field(
        default=BookletStatus.DRAFT,
        sa_column=Column(String, nullable=False, index=True),
    )
    cover_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb_column())
    template_data: list[str] = Field(default_factory=list, sa_column=_jsonb_column(list))
    template: str = Field(
        default="default",
        sa_column=Column(String, nullable=False, server_default="default"),
    )
    course_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("course.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, onupdate=datetime.utcnow),
    )
    created_by_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )


class BookletItem(SQLModel, table=True):
    """Positioned booklet item. Can be a lesson row or a chapter separator."""

    __tablename__ = "booklet_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    booklet_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("booklet.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    position: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    item_type: BookletItemType = Field(
        sa_column=Column(String, nullable=False, index=True),
    )
    lesson_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("lesson.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
    )
    custom_title: Optional[str] = Field(default=None)
    custom_intro: Optional[str] = Field(default=None)
    include_brief: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
    )
    chapter_title: Optional[str] = Field(default=None)
    chapter_subtitle: Optional[str] = Field(default=None)
    chapter_body: Optional[str] = Field(default=None)
    chapter_starts_new_page: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, default=True),
    )
    is_included: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, default=True),
    )
    added_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )
    added_by_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )


class BookletGeneration(SQLModel, table=True):
    """Append-only record of a generation event."""

    __tablename__ = "booklet_generation"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    booklet_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("booklet.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )

    status: GenerationStatus = Field(
        default=GenerationStatus.PENDING,
        sa_column=Column(String, nullable=False, index=True),
    )
    format: GenerationFormat = Field(sa_column=Column(String, nullable=False))

    requested_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, index=True),
    )
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    requested_by_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )

    file_path: Optional[str] = Field(default=None)
    file_size_bytes: Optional[int] = Field(default=None)
    file_hash: Optional[str] = Field(default=None)
    file_mime: Optional[str] = Field(default=None)

    # Reproducibility snapshot, populated by worker before rendering.
    content_snapshot: Dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb_column())
    parameters: Dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb_column())
    error: Optional[str] = Field(default=None)
