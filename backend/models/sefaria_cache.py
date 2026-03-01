"""SQLModel table model for Sefaria text cache."""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class SefariaCache(SQLModel, table=True):
    """Cache for Sefaria API results to avoid repeated calls for the same ref."""

    __tablename__ = "sefaria_cache"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    type: Optional[str] = None           # Source type (Torah, Mishnah, Gemara, etc.)
    work: Optional[str] = None           # Work title (e.g., Pirkei Avot)
    ref: Optional[str] = None            # Human-readable reference (e.g., 4.2)
    he_ref: Optional[str] = None         # Hebrew reference
    standard_slug: str = Field(index=True, unique=True)  # Sefaria slug (e.g., Pirkei_Avot.4.2)
    text_english: Optional[str] = None   # English text from Sefaria
    text_hebrew: Optional[str] = None    # Hebrew text from Sefaria
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
