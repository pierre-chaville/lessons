"""Configuration router — /config endpoints."""

from uuid import UUID
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

import config as config_module
from auth import require_roles, _extract_role
from database import get_session
from models.preference_versioning import PreferenceVersion, PreferenceVersionSource
from schemas.config import ConfigUpdate, PreferenceVersionResponse, RestoreConfigVersionRequest
from services.preference_versioning import (
    compute_preference_diff,
    get_preference_version,
    list_preference_versions,
    preference_snapshot_to_yaml,
    replace_preferences,
    restore_preference_version,
    update_preferences,
)

router = APIRouter(prefix="/config", tags=["Configuration"])


def _actor_from_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    return {"sub": claims.get("sub"), "role": _extract_role(claims)}


def _build_preference_version_response(
    version: PreferenceVersion,
    restored_from_version_number: int | None = None,
) -> PreferenceVersionResponse:
    return PreferenceVersionResponse(
        id=version.id,
        version_number=version.version_number,
        version_source=version.version_source,
        created_at=version.created_at,
        last_edited_at=version.last_edited_at,
        edit_count=version.edit_count,
        is_sealed=version.is_sealed,
        sealed_at=version.sealed_at,
        sealed_reason=version.sealed_reason,
        created_by_id=version.created_by_id,
        change_summary=version.change_summary,
        parent_version_id=version.parent_version_id,
        restored_from_id=version.restored_from_id,
        restored_from_version_number=restored_from_version_number,
        is_current=version.is_current,
        content=version.content,
    )


@router.get("")
def get_configuration(
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get the current application configuration."""
    try:
        return config_module.load_config()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load configuration: {str(e)}"
        )


@router.put("")
def update_configuration(
    config_update: ConfigUpdate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Update the application configuration."""
    try:
        version = update_preferences(
            session=session,
            updates=config_update.config,
            actor=_actor_from_claims(claims),
        )
        session.commit()
        updated_config = version.content
        return {"message": "Configuration updated successfully", "config": updated_config}
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}"
        )


@router.get("/versions", response_model=list[PreferenceVersionResponse])
def get_configuration_versions(
    limit: int = Query(50, le=100),
    before: int | None = Query(None),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """List global preferences versions."""
    versions = list_preference_versions(session=session, limit=limit, before=before)
    session.commit()
    restored_from_ids = [v.restored_from_id for v in versions if v.restored_from_id]
    restored_numbers: Dict[UUID, int] = {}
    if restored_from_ids:
        rows = session.exec(
            select(PreferenceVersion.id, PreferenceVersion.version_number).where(
                PreferenceVersion.id.in_(restored_from_ids),
            )
        ).all()
        restored_numbers = {row[0]: row[1] for row in rows}
    return [
        _build_preference_version_response(
            v,
            restored_numbers.get(v.restored_from_id) if v.restored_from_id else None,
        )
        for v in versions
    ]


@router.get("/versions/{version_id}", response_model=PreferenceVersionResponse)
def get_configuration_version(
    version_id: UUID,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Get one global preferences version."""
    try:
        version = get_preference_version(session, version_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Version not found")
    restored_from_version_number = None
    if version.restored_from_id:
        restored_from = session.get(PreferenceVersion, version.restored_from_id)
        if restored_from:
            restored_from_version_number = restored_from.version_number
    return _build_preference_version_response(version, restored_from_version_number)


@router.get("/versions/{version_id}/yaml")
def get_configuration_version_yaml(
    version_id: UUID,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Get one global preferences version as YAML."""
    try:
        version = get_preference_version(session, version_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"yaml": preference_snapshot_to_yaml(version.content)}


@router.get("/versions/{version_a}/diff/{version_b}")
def get_configuration_versions_diff(
    version_a: UUID,
    version_b: UUID,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Diff two global preferences versions as YAML."""
    try:
        a = get_preference_version(session, version_a)
        b = get_preference_version(session, version_b)
    except ValueError:
        raise HTTPException(status_code=404, detail="Version not found")
    return compute_preference_diff(a, b)


@router.post("/versions/{version_id}/restore", response_model=PreferenceVersionResponse)
def restore_configuration_version(
    version_id: UUID,
    body: RestoreConfigVersionRequest,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Restore global preferences from a historical snapshot."""
    try:
        restored = restore_preference_version(
            session=session,
            target_version_id=version_id,
            actor=_actor_from_claims(claims),
            reason=body.reason,
        )
        session.commit()
        session.refresh(restored)
        restored_from_version_number = None
        if restored.restored_from_id:
            restored_from = session.get(PreferenceVersion, restored.restored_from_id)
            if restored_from:
                restored_from_version_number = restored_from.version_number
        return _build_preference_version_response(restored, restored_from_version_number)
    except ValueError:
        session.rollback()
        raise HTTPException(status_code=404, detail="Version not found")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to restore configuration: {str(e)}"
        )


@router.get("/{key_path}")
def get_configuration_value(
    key_path: str,
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get a specific configuration value using dot notation (e.g., 'transcribe.model')."""
    try:
        value = config_module.get_config_value(key_path)
        if value is None:
            raise HTTPException(
                status_code=404, detail=f"Configuration key '{key_path}' not found"
            )
        return {"key": key_path, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get configuration value: {str(e)}"
        )


@router.post("/reset")
def reset_configuration(
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Reset configuration to default values."""
    try:
        version = replace_preferences(
            session=session,
            config=config_module.DEFAULT_CONFIG,
            actor=_actor_from_claims(claims),
            source=PreferenceVersionSource.HUMAN,
            change_summary="reset_to_defaults",
            coalesce_window_minutes=0,
        )
        session.commit()
        return {
            "message": "Configuration reset to defaults",
            "config": version.content,
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to reset configuration: {str(e)}"
        )
