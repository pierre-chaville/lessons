"""Glossary router — /glossary endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

import crud
from auth import require_roles
from database import get_session
from hashid_utils import decode_id, encode_id
from schemas.glossary import (
    GlossaryEntryCreate,
    GlossaryEntryResponse,
    GlossaryEntryUpdate,
)

router = APIRouter(prefix="/glossary", tags=["Glossary"])


def _build_glossary_response(entry) -> GlossaryEntryResponse:
    return GlossaryEntryResponse(
        id=entry.id,
        hashid=encode_id(entry.id),
        standard=entry.standard,
        variations=entry.variations or [],
        exact_case=bool(entry.exact_case),
    )


@router.get("", response_model=List[GlossaryEntryResponse])
def list_glossary_entries(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entries = crud.get_all_glossary_entries(session)
    return [_build_glossary_response(entry) for entry in entries]


@router.get("/{entry_hashid}", response_model=GlossaryEntryResponse)
def get_glossary_entry(
    entry_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entry_id = decode_id(entry_hashid)
    entry = crud.get_glossary_entry(session, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return _build_glossary_response(entry)


@router.post("", response_model=GlossaryEntryResponse, status_code=201)
def create_glossary_entry(
    body: GlossaryEntryCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entry = crud.create_glossary_entry(
        session=session,
        standard=body.standard,
        variations=body.variations,
        exact_case=body.exact_case,
    )
    return _build_glossary_response(entry)


@router.patch("/{entry_hashid}", response_model=GlossaryEntryResponse)
def update_glossary_entry(
    entry_hashid: str,
    body: GlossaryEntryUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entry_id = decode_id(entry_hashid)
    entry = crud.update_glossary_entry(
        session=session,
        entry_id=entry_id,
        standard=body.standard,
        variations=body.variations,
        exact_case=body.exact_case,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return _build_glossary_response(entry)


@router.delete("/{entry_hashid}", status_code=204)
def delete_glossary_entry(
    entry_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entry_id = decode_id(entry_hashid)
    if not crud.delete_glossary_entry(session, entry_id):
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return None
