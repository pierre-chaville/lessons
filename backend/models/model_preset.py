"""SQLModel table model for reusable model presets."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime, String
from sqlmodel import Field, SQLModel


class ModelPreset(SQLModel, table=True):
    """Admin-managed preset for LLM/model execution settings."""

    __tablename__ = "model_preset"
    __table_args__ = {"extend_existing": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False, index=True))
    provider: str = Field(sa_column=Column(String, nullable=False, index=True))
    model_id: str = Field(sa_column=Column(String, nullable=False))
    temperature: float = Field(default=0.7)
    cost_input_per_m_tokens: float = Field(default=0.0)
    cost_output_per_m_tokens: float = Field(default=0.0)
    flex_cost_ratio: float = Field(default=0.5)
    thinking_mode: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, onupdate=datetime.utcnow),
    )
