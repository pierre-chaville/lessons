"""Themes router — /themes endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles
from database import get_session
from models import Theme
from schemas.theme import ThemeCreate, ThemeUpdate

router = APIRouter(prefix="/themes", tags=["Themes"])


@router.get("", response_model=List[Theme])
def get_themes(session: Session = Depends(get_session)):
    """Get all themes."""
    return crud.get_all_themes(session)


@router.get("/{theme_id}", response_model=Theme)
def get_theme(theme_id: int, session: Session = Depends(get_session)):
    """Get a specific theme by ID."""
    theme = crud.get_theme(session, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.post("", response_model=Theme, status_code=201)
def create_theme(
    theme_data: ThemeCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Create a new theme."""
    return crud.create_theme(session, name=theme_data.name)


@router.patch("/{theme_id}", response_model=Theme)
def update_theme(
    theme_id: int,
    theme_data: ThemeUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Update an existing theme."""
    theme = crud.update_theme(session, theme_id, name=theme_data.name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.delete("/{theme_id}", status_code=204)
def delete_theme(
    theme_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Delete a theme."""
    if not crud.delete_theme(session, theme_id):
        raise HTTPException(status_code=404, detail="Theme not found")
    return None
