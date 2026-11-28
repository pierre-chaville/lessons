"""Pydantic schemas for model preset API."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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


# ── JSON export / import ──────────────────────────────────────────────────────
# Presets keep their id: configuration YAML references presets by
# `model_preset_id`, so ids must match between environments.


class ModelPresetTransfer(ModelPresetCreate):
    id: int = Field(gt=0)


class ModelPresetExport(BaseModel):
    format: Literal["model_presets"] = "model_presets"
    version: int = 1
    exported_at: datetime
    presets: List[ModelPresetTransfer]


class ModelPresetImportRequest(BaseModel):
    """Accepts an export file as-is: extra keys (format, version, exported_at) are ignored."""

    presets: List[ModelPresetTransfer]

    @field_validator("presets")
    @classmethod
    def _unique_ids(cls, presets: List[ModelPresetTransfer]) -> List[ModelPresetTransfer]:
        seen: set[int] = set()
        for preset in presets:
            if preset.id in seen:
                raise ValueError(f"Duplicate model preset id {preset.id}")
            seen.add(preset.id)
        return presets


class ModelPresetImportResult(BaseModel):
    created: int
    updated: int
    unchanged: int
    total: int
    # Presets present in the database but absent from the file (left untouched).
    ids_not_in_file: List[int]
