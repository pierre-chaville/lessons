"""Schemas for booklet APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from models.booklet import BookletItemType, BookletStatus, GenerationFormat, GenerationStatus


class BookletCreate(BaseModel):
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    cover_metadata: Dict[str, Any] = Field(default_factory=dict)
    template: str = "default"
    course_id: Optional[int] = None
    template_data: List[str] = Field(default_factory=list)


class BookletUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    cover_metadata: Optional[Dict[str, Any]] = None
    template: Optional[str] = None
    course_id: Optional[int] = None
    template_data: Optional[List[str]] = None


class BookletItemAdd(BaseModel):
    item_type: BookletItemType
    position: Optional[int] = None
    lesson_id: Optional[int] = None
    custom_title: Optional[str] = None
    custom_intro: Optional[str] = None
    include_brief: bool = False
    chapter_title: Optional[str] = None
    chapter_subtitle: Optional[str] = None
    chapter_body: Optional[str] = None
    chapter_starts_new_page: bool = True


class BookletLessonAdd(BaseModel):
    lesson_id: int
    position: Optional[int] = None
    custom_title: Optional[str] = None
    custom_intro: Optional[str] = None
    include_brief: bool = False


class BookletItemUpdate(BaseModel):
    custom_title: Optional[str] = None
    custom_intro: Optional[str] = None
    include_brief: Optional[bool] = None
    chapter_title: Optional[str] = None
    chapter_subtitle: Optional[str] = None
    chapter_body: Optional[str] = None
    chapter_starts_new_page: Optional[bool] = None
    is_included: Optional[bool] = None


class BookletLessonUpdate(BaseModel):
    custom_title: Optional[str] = None
    custom_intro: Optional[str] = None
    include_brief: Optional[bool] = None
    is_included: Optional[bool] = None


class BookletReorderRequest(BaseModel):
    item_ids: Optional[List[int]] = None
    lesson_ids: Optional[List[int]] = None


class BookletStatusChangeRequest(BaseModel):
    new_status: BookletStatus
    reason: Optional[str] = None


class BookletGenerationCreate(BaseModel):
    format: GenerationFormat
    parameters: Dict[str, Any] = Field(default_factory=dict)


class BookletItemResponse(BaseModel):
    id: int
    booklet_id: int
    position: int
    item_type: BookletItemType
    lesson_id: Optional[int]
    custom_title: Optional[str]
    custom_intro: Optional[str]
    include_brief: bool
    chapter_title: Optional[str]
    chapter_subtitle: Optional[str]
    chapter_body: Optional[str]
    chapter_starts_new_page: bool
    is_included: bool
    added_at: datetime
    added_by_id: Optional[str]
    lesson_title: Optional[str] = None
    lesson_status: Optional[str] = None

    class Config:
        from_attributes = True


class BookletResponse(BaseModel):
    id: int
    title: str
    subtitle: Optional[str]
    description: Optional[str]
    status: BookletStatus
    cover_metadata: Dict[str, Any]
    template_data: List[str] = Field(default_factory=list)
    template: str
    course_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[str]

    class Config:
        from_attributes = True


class BookletDetailResponse(BookletResponse):
    items: List[BookletItemResponse] = Field(default_factory=list)
    lessons: List[BookletItemResponse] = Field(default_factory=list)


class BookletGenerationResponse(BaseModel):
    id: UUID
    booklet_id: int
    status: GenerationStatus
    format: GenerationFormat
    requested_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    requested_by_id: Optional[str]
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    file_hash: Optional[str]
    file_mime: Optional[str]
    content_snapshot: Dict[str, Any]
    parameters: Dict[str, Any]
    error: Optional[str]

    class Config:
        from_attributes = True


class BookletListResponse(BaseModel):
    items: List[BookletResponse]
    total: int
    offset: int
    limit: int
