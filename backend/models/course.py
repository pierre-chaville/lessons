"""SQLModel table model for courses."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List


class Course(SQLModel, table=True):
    """Course model"""

    __tablename__ = "course"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None

    # Relationships
    lessons: List["Lesson"] = Relationship(back_populates="course")
