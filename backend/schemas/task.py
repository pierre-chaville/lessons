"""Pydantic schemas for task API requests and responses."""

from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class TaskCreate(BaseModel):
    task_type: str
    parameters: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    id: int
    task_type: str
    status: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    duration: Optional[float]
    parameters: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_by_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
