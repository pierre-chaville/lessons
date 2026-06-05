"""Versioning service for global preferences/configuration."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
from difflib import unified_diff
from typing import Any, Optional
from uuid import UUID

import yaml
from sqlalchemy.orm import load_only
from sqlmodel import Session, select

import config as config_module
from models.preference_versioning import PreferenceVersion, PreferenceVersionSource
from services.audit import log_event


def _actor_id(actor: Any) -> Optional[str]:
    if actor is None:
        return None
    if isinstance(actor, dict):
        return actor.get("sub")
    return getattr(actor, "id", None)


def preference_snapshot_to_yaml(content: Any) -> str:
    normalized = config_module.normalize_config(content if isinstance(content, dict) else {})
    return yaml.safe_dump(
        normalized,
        allow_unicode=True,
        sort_keys=True,
        width=120,
    )


def _same_content(old: Any, new: Any) -> bool:
    return config_module.normalize_config(old if isinstance(old, dict) else {}) == config_module.normalize_config(new)


def _current_version(session: Session) -> PreferenceVersion | None:
    return session.exec(
        select(PreferenceVersion)
        .where(PreferenceVersion.is_current == True)  # noqa: E712
        .with_for_update()
    ).first()


def ensure_current_version(
    session: Session,
    config: dict[str, Any] | None = None,
) -> PreferenceVersion:
    current = _current_version(session)
    if current is not None:
        return current

    normalized = config_module.normalize_config(
        config if config is not None else config_module.load_config_from_session(session)
    )
    last_version = session.exec(
        select(PreferenceVersion).order_by(PreferenceVersion.version_number.desc())
    ).first()
    now = datetime.utcnow()
    version = PreferenceVersion(
        content=normalized,
        version_number=(last_version.version_number + 1) if last_version else 1,
        version_source=PreferenceVersionSource.SYSTEM.value,
        created_at=now,
        last_edited_at=None,
        edit_count=1,
        is_sealed=True,
        sealed_at=now,
        sealed_reason="backfill",
        created_by_id=None,
        change_summary="Initial preferences snapshot",
        parent_version_id=last_version.id if last_version else None,
        is_current=True,
    )
    session.add(version)
    session.flush()
    return version


def seal_current_version(
    session: Session,
    reason: str,
    actor: Any | None,
) -> PreferenceVersion | None:
    current = _current_version(session)
    if current is None or current.is_sealed:
        return None

    now = datetime.utcnow()
    session_duration_seconds = 0
    if current.last_edited_at:
        session_duration_seconds = int((current.last_edited_at - current.created_at).total_seconds())
    current.is_sealed = True
    current.sealed_at = now
    current.sealed_reason = reason
    current.last_edited_at = None
    session.add(current)
    session.flush()

    log_event(
        session=session,
        actor=actor,
        entity_type="preferences",
        entity_id="global",
        action="preferences.sealed",
        payload={
            "version_id": str(current.id),
            "reason": reason,
            "edit_count": current.edit_count,
            "session_duration_seconds": session_duration_seconds,
        },
    )
    return current


def _write_preferences_version(
    session: Session,
    new_config: dict[str, Any],
    actor: Any | None,
    source: PreferenceVersionSource,
    change_summary: str | None = None,
    coalesce_window_minutes: int = 10,
    restored_from_id: UUID | None = None,
) -> PreferenceVersion:
    normalized = config_module.normalize_config(new_config)
    actor_id = _actor_id(actor)
    now = datetime.utcnow()

    tx_ctx = nullcontext() if session.in_transaction() else session.begin()
    with tx_ctx:
        current = ensure_current_version(session)

        if source == PreferenceVersionSource.HUMAN and _same_content(current.content, normalized):
            config_module.save_config_in_session(session, normalized)
            return current

        if source == PreferenceVersionSource.HUMAN and current is not None:
            within_window = (
                current.last_edited_at is not None
                and now - current.last_edited_at <= timedelta(minutes=coalesce_window_minutes)
            )
            if (
                not current.is_sealed
                and current.version_source == PreferenceVersionSource.HUMAN.value
                and current.created_by_id == actor_id
                and within_window
            ):
                current.content = normalized
                current.last_edited_at = now
                current.edit_count += 1
                if change_summary:
                    current.change_summary = (
                        f"{current.change_summary}; {change_summary}"
                        if current.change_summary
                        else change_summary
                    )
                session.add(current)
                config_module.save_config_in_session(session, normalized)
                session.flush()
                return current

        if current and not current.is_sealed:
            if source == PreferenceVersionSource.RESTORE:
                seal_reason = "restored_over"
            elif current.created_by_id and current.created_by_id != actor_id:
                seal_reason = "different_user"
            elif current.last_edited_at and (now - current.last_edited_at > timedelta(minutes=coalesce_window_minutes)):
                seal_reason = "window_expired"
            else:
                seal_reason = "source_changed"
            seal_current_version(session=session, reason=seal_reason, actor=actor)

        previous_current = _current_version(session)
        if previous_current:
            previous_current.is_current = False
            session.add(previous_current)

        last_version = session.exec(
            select(PreferenceVersion).order_by(PreferenceVersion.version_number.desc())
        ).first()
        version_number = (last_version.version_number + 1) if last_version else 1
        version = PreferenceVersion(
            content=normalized,
            version_number=version_number,
            version_source=source.value,
            created_at=now,
            last_edited_at=now if source == PreferenceVersionSource.HUMAN else None,
            edit_count=1,
            is_sealed=False,
            created_by_id=actor_id if source in (PreferenceVersionSource.HUMAN, PreferenceVersionSource.RESTORE) else None,
            change_summary=change_summary,
            parent_version_id=previous_current.id if previous_current else None,
            restored_from_id=restored_from_id,
            is_current=True,
        )
        session.add(version)
        config_module.save_config_in_session(session, normalized)
        session.flush()

        log_event(
            session=session,
            actor=actor if source != PreferenceVersionSource.SYSTEM else {"role": "system"},
            entity_type="preferences",
            entity_id="global",
            action="preferences.restored" if source == PreferenceVersionSource.RESTORE else "preferences.created",
            payload={
                "version_id": str(version.id),
                "version_number": version_number,
                "version_source": source.value,
                "created_by_id": actor_id if source in (PreferenceVersionSource.HUMAN, PreferenceVersionSource.RESTORE) else None,
                "change_summary": change_summary,
                "restored_from_id": str(restored_from_id) if restored_from_id else None,
            },
        )
        return version


def update_preferences(
    session: Session,
    updates: dict[str, Any],
    actor: Any,
    change_summary: str | None = None,
) -> PreferenceVersion:
    current_config = config_module.load_config_from_session(session)
    update_payload = updates or {}
    default_keys = set(config_module.DEFAULT_CONFIG.keys())
    is_full_snapshot = default_keys.issubset(set(update_payload.keys()))
    merged_config = (
        update_payload
        if is_full_snapshot
        else config_module.merge_dicts(current_config, update_payload)
    )
    return _write_preferences_version(
        session=session,
        new_config=merged_config,
        actor=actor,
        source=PreferenceVersionSource.HUMAN,
        change_summary=change_summary,
    )


def replace_preferences(
    session: Session,
    config: dict[str, Any],
    actor: Any | None,
    source: PreferenceVersionSource,
    change_summary: str | None = None,
    restored_from_id: UUID | None = None,
    coalesce_window_minutes: int = 10,
) -> PreferenceVersion:
    return _write_preferences_version(
        session=session,
        new_config=config,
        actor=actor,
        source=source,
        change_summary=change_summary,
        restored_from_id=restored_from_id,
        coalesce_window_minutes=coalesce_window_minutes,
    )


def restore_preference_version(
    session: Session,
    target_version_id: UUID,
    actor: Any,
    reason: str | None = None,
) -> PreferenceVersion:
    target = session.get(PreferenceVersion, target_version_id)
    if target is None:
        raise ValueError("Target version not found")
    if target.is_current:
        return target
    return replace_preferences(
        session=session,
        config=target.content,
        actor=actor,
        source=PreferenceVersionSource.RESTORE,
        change_summary=reason,
        restored_from_id=target.id,
    )


def list_preference_versions(
    session: Session,
    limit: int = 50,
    before: Optional[int] = None,
) -> list[PreferenceVersion]:
    ensure_current_version(session)
    statement = (
        select(PreferenceVersion)
        .options(
            load_only(
                PreferenceVersion.id,
                PreferenceVersion.version_number,
                PreferenceVersion.version_source,
                PreferenceVersion.created_at,
                PreferenceVersion.last_edited_at,
                PreferenceVersion.edit_count,
                PreferenceVersion.is_sealed,
                PreferenceVersion.sealed_at,
                PreferenceVersion.sealed_reason,
                PreferenceVersion.created_by_id,
                PreferenceVersion.change_summary,
                PreferenceVersion.parent_version_id,
                PreferenceVersion.restored_from_id,
                PreferenceVersion.is_current,
            )
        )
        .order_by(PreferenceVersion.version_number.desc())
        .limit(limit)
    )
    if before is not None:
        statement = statement.where(PreferenceVersion.version_number < before)
    return list(session.exec(statement).all())


def get_preference_version(session: Session, version_id: UUID) -> PreferenceVersion:
    row = session.get(PreferenceVersion, version_id)
    if row is None:
        raise ValueError("Version not found")
    return row


def compute_preference_diff(version_a: PreferenceVersion, version_b: PreferenceVersion) -> dict[str, Any]:
    a_text = preference_snapshot_to_yaml(version_a.content)
    b_text = preference_snapshot_to_yaml(version_b.content)
    lines = list(
        unified_diff(
            a_text.splitlines(),
            b_text.splitlines(),
            fromfile=f"preferences-v{version_a.version_number}.yaml",
            tofile=f"preferences-v{version_b.version_number}.yaml",
            lineterm="",
        )
    )
    return {"type": "text", "diff": "\n".join(lines)}
