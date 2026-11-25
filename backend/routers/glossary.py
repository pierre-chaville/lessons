"""Glossary router — /glossary endpoints (Hebrew-keyed glossary)."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlmodel import Session
import yaml

import crud
from auth import require_roles
from database import get_session
from hashid_utils import decode_id, encode_id
from hebrew_text import normalize_hebrew
from models.glossary import GlossaryEntry
from services.glossary_completion import GLOSSARY_TASK_TYPE, enqueue_glossary_completion
from schemas.glossary import (
    GlossaryCompletionLaunch,
    GlossaryCompletionStatus,
    GlossaryEntryCreate,
    GlossaryEntryListResponse,
    GlossaryEntryResponse,
    GlossaryEntryUpdate,
    GlossaryImportResult,
    GlossaryStatus,
    GlossaryType,
)

router = APIRouter(prefix="/glossary", tags=["Glossary"])

READ_ROLES = ["editor", "publisher", "admin"]
WRITE_ROLES = ["publisher", "admin"]

# Fields that cannot be cleared with an explicit null in a PATCH.
_NON_NULLABLE_FIELDS = {"hebrew", "aliases", "type", "case_flag", "status", "source"}
# Field order of an exported entry (hebrew_norm / hebrew_cons are derived on import).
_EXPORT_FIELDS = (
    "hebrew",
    "hebrew_norm",
    "hebrew_cons",
    "translit",
    "aliases",
    "type",
    "case_flag",
    "status",
    "source",
    "context_lesson",
    "context_paragraph",
    "translation",
    "sefaria_title",
    "sefaria_ref",
)


def _build_glossary_response(entry: GlossaryEntry) -> GlossaryEntryResponse:
    return GlossaryEntryResponse(
        id=entry.id,
        hashid=encode_id(entry.id),
        hebrew=entry.hebrew,
        hebrew_norm=entry.hebrew_norm,
        hebrew_cons=entry.hebrew_cons,
        translit=entry.translit,
        aliases=entry.aliases or [],
        type=entry.type,
        case_flag=entry.case_flag,
        status=entry.status,
        source=entry.source,
        context_lesson=entry.context_lesson,
        context_paragraph=entry.context_paragraph,
        translation=entry.translation,
        sefaria_title=entry.sefaria_title,
        sefaria_ref=entry.sefaria_ref,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _conflict(hebrew_norm: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"A glossary entry already exists for '{hebrew_norm}'",
    )


def _yaml_response(payload: list[dict[str, Any]], filename: str) -> Response:
    content = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return Response(
        content=content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=GlossaryEntryListResponse)
def list_glossary_entries(
    q: str | None = Query(default=None, description="Search Hebrew (niqqud ignored), transliteration, aliases or translation"),
    type: GlossaryType | None = Query(default=None),
    status_filter: GlossaryStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(READ_ROLES)),
):
    entries, total = crud.list_glossary_entries(
        session,
        query=q,
        entry_type=type.value if type else None,
        status=status_filter.value if status_filter else None,
        page=page,
        per_page=per_page,
    )
    return GlossaryEntryListResponse(
        items=[_build_glossary_response(entry) for entry in entries],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/export/yaml")
def export_glossary_yaml(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(READ_ROLES)),
):
    entries = crud.get_all_glossary_entries(session)
    payload = [
        {field: getattr(entry, field) for field in _EXPORT_FIELDS}
        for entry in entries
    ]
    for item in payload:
        item["aliases"] = list(item["aliases"] or [])
    return _yaml_response(payload, "glossary.yaml")


@router.get("/legacy/export/yaml")
def export_legacy_glossary_yaml(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(READ_ROLES)),
):
    """Backup of the legacy transliteration glossary (standard + variations)."""
    entries = crud.get_all_legacy_glossary_entries(session)
    payload = [
        {
            "standard": entry.standard,
            "variations": entry.variations or [],
            "exactCase": bool(entry.exact_case),
        }
        for entry in entries
    ]
    return _yaml_response(payload, "glossary_legacy.yaml")


@router.post("/import/yaml", response_model=GlossaryImportResult)
async def import_glossary_yaml(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    """Upsert entries keyed by hebrew_norm. Fields missing from an item are left unchanged."""
    raw = (await file.read()).decode("utf-8", errors="replace")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail="Invalid YAML file") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="YAML must contain a list of glossary entries")

    payloads: list[GlossaryEntryCreate] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"Glossary entry #{index} is not a mapping")
        # Derived keys are recomputed from `hebrew`.
        item = {k: v for k, v in item.items() if k not in ("hebrew_norm", "hebrew_cons")}
        try:
            payloads.append(GlossaryEntryCreate(**item))
        except ValidationError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid glossary entry #{index} in YAML: {exc}"
            ) from exc

    created = 0
    updated = 0
    for payload in payloads:
        existing = crud.get_glossary_entry_by_hebrew_norm(session, normalize_hebrew(payload.hebrew))
        if existing:
            crud.update_glossary_entry(session, existing.id, payload.model_dump(exclude_unset=True))
            updated += 1
        else:
            crud.create_glossary_entry(session, payload.model_dump())
            created += 1

    return GlossaryImportResult(created=created, updated=updated, total=created + updated)


@router.post("/complete", response_model=GlossaryCompletionLaunch)
def complete_glossary_entries(
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    """Queue an LLM task completing entries without transliteration.

    Reuses the pending/running glossary task if there is one; no task is
    created when nothing needs completion.
    """
    pending = crud.count_glossary_entries_to_complete(session)
    task_id = enqueue_glossary_completion(session, created_by_id=claims.get("sub"))
    return GlossaryCompletionLaunch(task_id=task_id, pending_entries=pending)


@router.get("/complete/status", response_model=GlossaryCompletionStatus)
def glossary_completion_status(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    """Number of entries awaiting completion and the latest completion task.

    Publisher/admin only, like starting the task (editors don't see tasks
    that are not tied to a lesson they are assigned to).
    """
    task = crud.get_latest_task_of_type(session, GLOSSARY_TASK_TYPE)
    return GlossaryCompletionStatus(
        pending_entries=crud.count_glossary_entries_to_complete(session),
        task_id=task.id if task else None,
        task_status=task.status if task else None,
        task_error=task.error if task else None,
        task_result=task.result if task else None,
    )


@router.get("/{entry_hashid}", response_model=GlossaryEntryResponse)
def get_glossary_entry(
    entry_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(READ_ROLES)),
):
    entry = crud.get_glossary_entry(session, decode_id(entry_hashid))
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return _build_glossary_response(entry)


@router.post("", response_model=GlossaryEntryResponse, status_code=status.HTTP_201_CREATED)
def create_glossary_entry(
    body: GlossaryEntryCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    try:
        entry = crud.create_glossary_entry(session, body.model_dump())
    except crud.GlossaryConflictError as exc:
        raise _conflict(str(exc)) from exc
    return _build_glossary_response(entry)


@router.patch("/{entry_hashid}", response_model=GlossaryEntryResponse)
def update_glossary_entry(
    entry_hashid: str,
    body: GlossaryEntryUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    fields = body.model_dump(exclude_unset=True)
    cleared = sorted(name for name in _NON_NULLABLE_FIELDS if name in fields and fields[name] is None)
    if cleared:
        raise HTTPException(status_code=422, detail=f"Fields cannot be null: {', '.join(cleared)}")
    try:
        entry = crud.update_glossary_entry(session, decode_id(entry_hashid), fields)
    except crud.GlossaryConflictError as exc:
        raise _conflict(str(exc)) from exc
    if not entry:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return _build_glossary_response(entry)


@router.delete("/{entry_hashid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_glossary_entry(
    entry_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(WRITE_ROLES)),
):
    if not crud.delete_glossary_entry(session, decode_id(entry_hashid)):
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    return None
