"""Model presets router — /model-presets endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

import crud
from auth import require_roles
from database import get_session
from schemas.model_preset import (
    ModelPresetCreate,
    ModelPresetResponse,
    ModelPresetUpdate,
)

router = APIRouter(prefix="/model-presets", tags=["Model Presets"])


@router.get("", response_model=List[ModelPresetResponse])
def get_model_presets(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Get all model presets."""
    return crud.get_all_model_presets(session)


@router.get("/{preset_id}", response_model=ModelPresetResponse)
def get_model_preset(
    preset_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Get a model preset by ID."""
    preset = crud.get_model_preset(session, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Model preset not found")
    return preset


@router.post("", response_model=ModelPresetResponse, status_code=201)
def create_model_preset(
    payload: ModelPresetCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Create a model preset."""
    return crud.create_model_preset(
        session,
        name=payload.name,
        provider=payload.provider,
        model_id=payload.model_id,
        temperature=payload.temperature,
        cost_input_per_m_tokens=payload.cost_input_per_m_tokens,
        cost_output_per_m_tokens=payload.cost_output_per_m_tokens,
        flex_cost_ratio=payload.flex_cost_ratio,
        thinking_mode=payload.thinking_mode,
    )


@router.patch("/{preset_id}", response_model=ModelPresetResponse)
def update_model_preset(
    preset_id: int,
    payload: ModelPresetUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Update a model preset."""
    preset = crud.update_model_preset(
        session,
        preset_id=preset_id,
        name=payload.name,
        provider=payload.provider,
        model_id=payload.model_id,
        temperature=payload.temperature,
        cost_input_per_m_tokens=payload.cost_input_per_m_tokens,
        cost_output_per_m_tokens=payload.cost_output_per_m_tokens,
        flex_cost_ratio=payload.flex_cost_ratio,
        thinking_mode=payload.thinking_mode,
    )
    if not preset:
        raise HTTPException(status_code=404, detail="Model preset not found")
    return preset


@router.delete("/{preset_id}", status_code=204)
def delete_model_preset(
    preset_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Delete a model preset."""
    deleted = crud.delete_model_preset(session, preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model preset not found")
    return None
