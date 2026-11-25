"""SQLModel table model for per-user display preferences."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class UserPreference(SQLModel, table=True):
    """Personal settings of one user, shared across their devices.

    Keyed by the Clerk user id (JWT ``sub``): a user only ever reads and
    writes their own row (see AGENTS.md › Access Control › My preferences).
    """

    __tablename__ = "user_preference"
    __table_args__ = {"extend_existing": True}

    user_id: str = Field(sa_column=Column(String, primary_key=True))
    # How Hebrew terms are displayed in lessons (schemas.user_preference.HebrewDisplaySettings).
    hebrew_display: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False),
    )
