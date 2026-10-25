"""SQLModel table model for themes."""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List


class Theme(SQLModel, table=True):
    """Theme model — supports hierarchical nesting via parent_id."""

    __tablename__ = "theme"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = Field(default=None, foreign_key="theme.id", index=True)
    sort_order: int = Field(default=0)

    children: List["Theme"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"foreign_keys": "[Theme.parent_id]"},
    )
    parent: Optional["Theme"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "[Theme.id]"},
    )
