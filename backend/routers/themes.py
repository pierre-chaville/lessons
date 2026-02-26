"""Themes router — /themes endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles
from database import get_session
from schemas.theme import ThemeCreate, ThemeUpdate, ThemeResponse
from hashid_utils import encode_id, decode_id

router = APIRouter(prefix="/themes", tags=["Themes"])


def _build_theme_response(theme) -> ThemeResponse:
    """Build a ThemeResponse with hashid from a Theme DB model."""
    return ThemeResponse(
        id=theme.id,
        hashid=encode_id(theme.id),
        name=theme.name,
    )


@router.get("", response_model=List[ThemeResponse])
def get_themes(session: Session = Depends(get_session)):
    """Get all themes."""
    themes = crud.get_all_themes(session)
    return [_build_theme_response(t) for t in themes]


@router.get("/{theme_hashid}", response_model=ThemeResponse)
def get_theme(theme_hashid: str, session: Session = Depends(get_session)):
    """Get a specific theme by hashid."""
    theme_id = decode_id(theme_hashid)
    theme = crud.get_theme(session, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return _build_theme_response(theme)


@router.post("", response_model=ThemeResponse, status_code=201)
def create_theme(
    theme_data: ThemeCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Create a new theme."""
    theme = crud.create_theme(session, name=theme_data.name)
    return _build_theme_response(theme)


@router.patch("/{theme_hashid}", response_model=ThemeResponse)
def update_theme(
    theme_hashid: str,
    theme_data: ThemeUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Update an existing theme."""
    theme_id = decode_id(theme_hashid)
    theme = crud.update_theme(session, theme_id, name=theme_data.name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return _build_theme_response(theme)


@router.delete("/{theme_hashid}", status_code=204)
def delete_theme(
    theme_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a theme."""
    theme_id = decode_id(theme_hashid)
    if not crud.delete_theme(session, theme_id):
        raise HTTPException(status_code=404, detail="Theme not found")
    return None
