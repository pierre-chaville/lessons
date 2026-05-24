"""SQLModel table model for transliteration glossary entries."""

from typing import List, Optional

from sqlalchemy import JSON, Boolean, Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class GlossaryEntry(SQLModel, table=True):
    """Admin/publisher managed glossary entry."""

    __tablename__ = "glossary_entry"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    standard: str = Field(sa_column=Column(String, nullable=False, index=True))
    variations: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False),
    )
    exact_case: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
