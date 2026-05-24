"""Glossary router — /glossary endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlmodel import Session
import yaml

import crud
from auth import require_roles
from database import get_session
from hashid_utils import decode_id, encode_id
from schemas.glossary import (
    GlossaryEntryCreate,
    GlossaryImportResult,
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


@router.get("/export/yaml")
def export_glossary_yaml(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    entries = crud.get_all_glossary_entries(session)
    payload = [
        {
            "standard": entry.standard,
            "variations": entry.variations or [],
            "exactCase": bool(entry.exact_case),
        }
        for entry in entries
    ]
    content = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return Response(
        content=content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": 'attachment; filename="glossary.yaml"'},
    )


@router.post("/import/yaml", response_model=GlossaryImportResult)
async def import_glossary_yaml(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    raw = (await file.read()).decode("utf-8", errors="replace")
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="YAML must contain a list of glossary entries")

    existing_entries = crud.get_all_glossary_entries(session)
    existing_by_standard = {entry.standard.lower(): entry for entry in existing_entries}
    created = 0
    updated = 0

    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            payload = GlossaryEntryCreate(
                standard=item.get("standard", ""),
                variations=item.get("variations", []) or [],
                exact_case=(
                    item.get("exactCase")
                    if "exactCase" in item
                    else item.get("exact_case", False)
                ),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid glossary entry in YAML: {exc}") from exc
        key = payload.standard.lower()
        existing = existing_by_standard.get(key)
        if existing:
            crud.update_glossary_entry(
                session=session,
                entry_id=existing.id,
                standard=payload.standard,
                variations=payload.variations,
                exact_case=payload.exact_case,
            )
            updated += 1
        else:
            created_entry = crud.create_glossary_entry(
                session=session,
                standard=payload.standard,
                variations=payload.variations,
                exact_case=payload.exact_case,
            )
            existing_by_standard[key] = created_entry
            created += 1

    return GlossaryImportResult(
        created=created,
        updated=updated,
        total=created + updated,
    )


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
