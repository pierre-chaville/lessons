"""SQLModel table model for background tasks."""

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON
from typing import Optional, Dict, Any
from datetime import datetime


class Task(SQLModel, table=True):
    """Background task tracking"""

    __tablename__ = "task"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    task_type: str  # Type of task (e.g., "transcription", "correction", "summary")
    status: str = Field(default="pending")  # pending, running, completed, failed
    start_date: Optional[datetime] = None  # When task started
    end_date: Optional[datetime] = None  # When task completed/failed
    duration: Optional[float] = None  # Duration in seconds
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Task parameters
    result: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )  # Task result
    error: Optional[str] = None  # Error message if failed
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )  # When task was created
