"""SQLModel table models for the glossary.

- ``GlossaryEntry``: Hebrew-keyed glossary (key: ``hebrew_norm``).
- ``LegacyGlossaryEntry``: previous transliteration glossary (standard form +
  variants). Read-only; still drives the pipeline's spelling normalization
  until its entries are migrated to ``GlossaryEntry``.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _json_list_column() -> Column:
    return Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)


class GlossaryEntry(SQLModel, table=True):
    """Hebrew-keyed glossary entry (see schemas.glossary for allowed values)."""

    __tablename__ = "glossary_entry"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    # Display form, with niqqud, as validated.
    hebrew: str = Field(sa_column=Column(String, nullable=False))
    # Exact search key (see hebrew_text.normalize_hebrew). Unique identifier.
    hebrew_norm: str = Field(sa_column=Column(String, nullable=False, unique=True, index=True))
    # Fallback search key without niqqud (see hebrew_text.hebrew_consonants).
    hebrew_cons: str = Field(sa_column=Column(String, nullable=False, index=True))
    translit: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True, index=True))
    aliases: List[str] = Field(default_factory=list, sa_column=_json_list_column())
    type: str = Field(default="term", sa_column=Column(String, nullable=False, index=True))
    case_flag: str = Field(default="lower", sa_column=Column(String, nullable=False))
    status: str = Field(default="auto", sa_column=Column(String, nullable=False, index=True))
    source: str = Field(default="manual", sa_column=Column(String, nullable=False))
    context_lesson: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    context_paragraph: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    translation: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    sefaria_title: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    sefaria_ref: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )


class LegacyGlossaryEntry(SQLModel, table=True):
    """Previous transliteration glossary entry (read-only)."""

    __tablename__ = "glossary_legacy_entry"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    standard: str = Field(sa_column=Column(String, nullable=False, index=True))
    variations: List[str] = Field(default_factory=list, sa_column=_json_list_column())
    exact_case: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
