"""SQLModel table model for courses."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List


class Course(SQLModel, table=True):
    """Course model — supports hierarchical nesting via parent_id."""

    __tablename__ = "course"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = Field(default=None, foreign_key="course.id", index=True)

    # Relationships
    lessons: List["Lesson"] = Relationship(back_populates="course")
    children: List["Course"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"foreign_keys": "[Course.parent_id]"},
    )
    parent: Optional["Course"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "[Course.id]"},
    )
