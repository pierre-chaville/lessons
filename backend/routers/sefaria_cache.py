"""Sefaria cache router — /sefaria-cache endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles
from database import get_session
from schemas.sefaria_cache import SefariaCacheCreate, SefariaCacheUpdate, SefariaCacheResponse

router = APIRouter(prefix="/sefaria-cache", tags=["Sefaria Cache"])


def _build_response(entry) -> SefariaCacheResponse:
    """Build a SefariaCacheResponse from a SefariaCache DB model."""
    return SefariaCacheResponse(
        id=entry.id,
        type=entry.type,
        work=entry.work,
        ref=entry.ref,
        he_ref=entry.he_ref,
        standard_slug=entry.standard_slug,
        text_english=entry.text_english,
        text_hebrew=entry.text_hebrew,
        fetched_at=entry.fetched_at,
    )


@router.get("", response_model=List[SefariaCacheResponse])
def list_cache(session: Session = Depends(get_session)):
    """Get all cached Sefaria entries."""
    entries = crud.get_all_sefaria_cache(session)
    return [_build_response(e) for e in entries]


@router.get("/{standard_slug:path}", response_model=SefariaCacheResponse)
def get_cache_by_slug(standard_slug: str, session: Session = Depends(get_session)):
    """Get a cached Sefaria entry by its standard slug."""
    entry = crud.get_sefaria_cache_by_slug(session, standard_slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return _build_response(entry)


@router.post("", response_model=SefariaCacheResponse, status_code=201)
def create_cache(
    data: SefariaCacheCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Create or update a Sefaria cache entry (upsert by standard_slug)."""
    entry = crud.upsert_sefaria_cache(
        session,
        standard_slug=data.standard_slug,
        type=data.type,
        work=data.work,
        ref=data.ref,
        he_ref=data.he_ref,
        text_english=data.text_english,
        text_hebrew=data.text_hebrew,
    )
    return _build_response(entry)


@router.patch("/{standard_slug:path}", response_model=SefariaCacheResponse)
def update_cache(
    standard_slug: str,
    data: SefariaCacheUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Update a cached Sefaria entry."""
    entry = crud.get_sefaria_cache_by_slug(session, standard_slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    entry = crud.upsert_sefaria_cache(
        session,
        standard_slug=standard_slug,
        type=data.type,
        work=data.work,
        ref=data.ref,
        he_ref=data.he_ref,
        text_english=data.text_english,
        text_hebrew=data.text_hebrew,
    )
    return _build_response(entry)


@router.delete("/{cache_id}", status_code=204)
def delete_cache(
    cache_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a cached Sefaria entry."""
    if not crud.delete_sefaria_cache(session, cache_id):
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return None
