"""Pydantic schemas for model preset API."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ModelPresetCreate(BaseModel):
    name: str
    provider: str
    model_id: str
    temperature: float = 0.7
    cost_input_per_m_tokens: float = Field(default=0.0, ge=0)
    cost_output_per_m_tokens: float = Field(default=0.0, ge=0)
    flex_cost_ratio: float = Field(default=0.5, ge=0)
    thinking_mode: Dict[str, Any] = Field(default_factory=dict)


class ModelPresetUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    temperature: Optional[float] = None
    cost_input_per_m_tokens: Optional[float] = Field(default=None, ge=0)
    cost_output_per_m_tokens: Optional[float] = Field(default=None, ge=0)
    flex_cost_ratio: Optional[float] = Field(default=None, ge=0)
    thinking_mode: Optional[Dict[str, Any]] = None


class ModelPresetResponse(BaseModel):
    id: int
    name: str
    provider: str
    model_id: str
    temperature: float
    cost_input_per_m_tokens: float
    cost_output_per_m_tokens: float
    flex_cost_ratio: float
    thinking_mode: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
