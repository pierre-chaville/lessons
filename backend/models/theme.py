"""SQLModel table model for themes."""

from sqlmodel import SQLModel, Field
from typing import Optional


class Theme(SQLModel, table=True):
    """Theme model"""

    __tablename__ = "theme"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
