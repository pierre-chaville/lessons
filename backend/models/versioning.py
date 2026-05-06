"""Versioning models for lesson editable content."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _jsonb_column() -> Column:
    """Use JSONB on PostgreSQL and JSON elsewhere (tests/dev sqlite)."""
    return Column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)


class ContentType(str, Enum):
    TITLE = "title"
    CORRECTED_TRANSCRIPT = "corrected_transcript"
    EDITED_TRANSCRIPT = "edited_transcript"
    BRIEF = "brief"
    SUMMARY = "summary"


class VersionSource(str, Enum):
    HUMAN = "human"
    PIPELINE = "pipeline"
    RESTORE = "restore"


class ContentVersion(SQLModel, table=True):
    """Full snapshot of one editable lesson field at one version/session."""

    __tablename__ = "content_version"
    __table_args__ = (
        UniqueConstraint(
            "lesson_id",
            "content_type",
            "version_number",
            name="uq_content_version_number",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    lesson_id: int = Field(
        foreign_key="lesson.id",
        index=True,
        sa_column_kwargs={"nullable": False},
    )
    content_type: ContentType = Field(
        sa_column=Column(String, nullable=False, index=True),
    )
    content: Any = Field(sa_column=_jsonb_column())
    version_number: int = Field(
        sa_column=Column(Integer, nullable=False),
    )
    version_source: VersionSource = Field(
        sa_column=Column(String, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, index=True),
    )
    last_edited_at: Optional[datetime] = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=True),
    )
    edit_count: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    is_sealed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    sealed_at: Optional[datetime] = Field(default=None)
    sealed_reason: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(default=None, index=True)
    change_summary: Optional[str] = Field(default=None)
    parent_version_id: Optional[UUID] = Field(default=None, foreign_key="content_version.id")
    restored_from_id: Optional[UUID] = Field(default=None, foreign_key="content_version.id")
    is_current: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
