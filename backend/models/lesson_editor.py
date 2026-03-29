"""SQLModel table model for lesson editors (many-to-many assignment)."""

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class LessonEditor(SQLModel, table=True):
    """Tracks which users are assigned as editors for a lesson."""

    __tablename__ = "lesson_editor"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    user_id: str = Field(index=True)
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_by: Optional[str] = None
