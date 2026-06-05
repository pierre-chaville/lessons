"""Pydantic schemas for configuration API requests."""

from pydantic import BaseModel
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime


class ConfigUpdate(BaseModel):
    config: Dict[str, Any]


class RestoreConfigVersionRequest(BaseModel):
    reason: str


class PreferenceVersionResponse(BaseModel):
    id: UUID
    version_number: int
    version_source: str
    created_at: datetime
    last_edited_at: Optional[datetime] = None
    edit_count: int
    is_sealed: bool
    sealed_at: Optional[datetime] = None
    sealed_reason: Optional[str] = None
    created_by_id: Optional[str] = None
    change_summary: Optional[str] = None
    parent_version_id: Optional[UUID] = None
    restored_from_id: Optional[UUID] = None
    restored_from_version_number: Optional[int] = None
    is_current: bool
    content: Optional[Any] = None
