"""Content versioning service."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
from difflib import unified_diff
import json
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import load_only
from sqlmodel import Session, select

from models.lesson import Lesson
from models.versioning import ContentType, ContentVersion, VersionSource
from schemas.lesson import EditedParagraph, Segment
from services.audit import log_event


def _normalize_content(content_type: ContentType, value: Any) -> Any:
    if content_type in (ContentType.TITLE, ContentType.BRIEF, ContentType.SUMMARY):
        if not isinstance(value, str):
            raise ValueError(f"{content_type.value} must be a string")
        return value

    if content_type == ContentType.CORRECTED_TRANSCRIPT:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, list):
            raise ValueError("corrected_transcript must be a list")
        return [Segment.model_validate(v).model_dump() for v in value]

    if content_type == ContentType.EDITED_TRANSCRIPT:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, list):
            raise ValueError("edited_transcript must be a list")
        return [EditedParagraph.model_validate(v).model_dump() for v in value]

    raise ValueError(f"Unsupported content type: {content_type}")


def _cache_to_lesson(lesson: Lesson, content_type: ContentType, value: Any) -> None:
    if content_type == ContentType.TITLE:
        lesson.title = value
    elif content_type == ContentType.CORRECTED_TRANSCRIPT:
        lesson.corrected_transcript = value
    elif content_type == ContentType.EDITED_TRANSCRIPT:
        lesson.edited_transcript = value
    elif content_type == ContentType.BRIEF:
        lesson.brief = value
    elif content_type == ContentType.SUMMARY:
        lesson.summary = value


def _same_content(content_type: ContentType, old: Any, new: Any) -> bool:
    normalized_new = _normalize_content(content_type, new)
    try:
        normalized_old = _normalize_content(content_type, old)
    except ValueError:
        # Legacy/invalid previous payloads should not block writing fresh content.
        return False
    return normalized_old == normalized_new


def _actor_id(actor: Any) -> Optional[str]:
    if actor is None:
        return None
    if isinstance(actor, dict):
        return actor.get("sub")
    return getattr(actor, "id", None)


def _actor_role(actor: Any) -> str:
    if actor is None:
        return "pipeline"
    if isinstance(actor, dict):
        metadata = actor.get("public_metadata") or {}
        return str(actor.get("role") or metadata.get("role") or "unknown")
    return str(getattr(actor, "role", "unknown"))


def seal_current_version(
    session: Session,
    lesson_id: int,
    content_type: ContentType,
    reason: str,
    actor: Any | None,
) -> ContentVersion | None:
    statement = (
        select(ContentVersion)
        .where(
            ContentVersion.lesson_id == lesson_id,
            ContentVersion.content_type == content_type.value,
            ContentVersion.is_current == True,  # noqa: E712
        )
        .with_for_update()
    )
    current = session.exec(statement).first()
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
        entity_type="lesson",
        entity_id=str(lesson_id),
        action=f"{content_type.value}.sealed",
        payload={
            "version_id": str(current.id),
            "lesson_id": lesson_id,
            "content_type": content_type.value,
            "reason": reason,
            "edit_count": current.edit_count,
            "session_duration_seconds": session_duration_seconds,
        },
    )
    return current


def seal_all_current_versions(
    session: Session,
    lesson_id: int,
    reason: str,
    actor: Any | None,
) -> None:
    rows = list(
        session.exec(
            select(ContentVersion).where(
                ContentVersion.lesson_id == lesson_id,
                ContentVersion.is_current == True,  # noqa: E712
            )
        ).all()
    )
    for row in rows:
        seal_current_version(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType(row.content_type),
            reason=reason,
            actor=actor,
        )


def update_content(
    session: Session,
    lesson_id: int,
    content_type: ContentType,
    new_content: Any,
    actor: Any | None,
    source: VersionSource = VersionSource.HUMAN,
    change_summary: str | None = None,
    coalesce_window_minutes: int = 10,
    emit_created_audit: bool = True,
) -> ContentVersion:
    """Create/coalesce content versions and mirror to lesson cache column."""
    normalized = _normalize_content(content_type, new_content)
    actor_id = _actor_id(actor)
    now = datetime.utcnow()

    tx_ctx = nullcontext() if session.in_transaction() else session.begin()
    with tx_ctx:
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            raise ValueError(f"Lesson {lesson_id} not found")

        current = session.exec(
            select(ContentVersion)
            .where(
                ContentVersion.lesson_id == lesson_id,
                ContentVersion.content_type == content_type.value,
                ContentVersion.is_current == True,  # noqa: E712
            )
            .with_for_update()
        ).first()

        if current and _same_content(content_type, current.content, normalized):
            return current

        if source == VersionSource.HUMAN and current is not None:
            within_window = (
                current.last_edited_at is not None
                and now - current.last_edited_at <= timedelta(minutes=coalesce_window_minutes)
            )
            if (
                not current.is_sealed
                and current.version_source == VersionSource.HUMAN.value
                and current.created_by_id == actor_id
                and within_window
            ):
                current.content = normalized
                current.last_edited_at = now
                current.edit_count += 1
                if change_summary:
                    if current.change_summary:
                        current.change_summary = f"{current.change_summary}; {change_summary}"
                    else:
                        current.change_summary = change_summary
                _cache_to_lesson(lesson, content_type, normalized)
                session.add(lesson)
                session.add(current)
                session.flush()
                return current

        if current and not current.is_sealed:
            if source == VersionSource.RESTORE:
                seal_reason = "restored_over"
            elif source == VersionSource.PIPELINE:
                seal_reason = "pipeline_rerun"
            elif current.created_by_id and current.created_by_id != actor_id:
                seal_reason = "different_user"
            elif current.last_edited_at and (now - current.last_edited_at > timedelta(minutes=coalesce_window_minutes)):
                seal_reason = "window_expired"
            else:
                seal_reason = "source_changed"
            seal_current_version(
                session=session,
                lesson_id=lesson_id,
                content_type=content_type,
                reason=seal_reason,
                actor=actor,
            )

        previous_current = session.exec(
            select(ContentVersion)
            .where(
                ContentVersion.lesson_id == lesson_id,
                ContentVersion.content_type == content_type.value,
                ContentVersion.is_current == True,  # noqa: E712
            )
            .with_for_update()
        ).first()
        if previous_current:
            previous_current.is_current = False
            session.add(previous_current)

        last_version = session.exec(
            select(ContentVersion)
            .where(
                ContentVersion.lesson_id == lesson_id,
                ContentVersion.content_type == content_type.value,
            )
            .order_by(ContentVersion.version_number.desc())
        ).first()
        version_number = (last_version.version_number + 1) if last_version else 1

        new_version = ContentVersion(
            lesson_id=lesson_id,
            content_type=content_type.value,
            content=normalized,
            version_number=version_number,
            version_source=source.value,
            created_at=now,
            last_edited_at=now if source == VersionSource.HUMAN else None,
            edit_count=1,
            is_sealed=False,
            created_by_id=actor_id if source == VersionSource.HUMAN else None,
            change_summary=change_summary,
            parent_version_id=previous_current.id if previous_current else None,
            is_current=True,
        )
        session.add(new_version)
        _cache_to_lesson(lesson, content_type, normalized)
        session.add(lesson)
        session.flush()

        if emit_created_audit:
            log_event(
                session=session,
                actor=actor if source != VersionSource.PIPELINE else {"role": "pipeline"},
                entity_type="lesson",
                entity_id=str(lesson_id),
                action=f"{content_type.value}.created",
                payload={
                    "version_id": str(new_version.id),
                    "lesson_id": lesson_id,
                    "content_type": content_type.value,
                    "version_number": version_number,
                    "version_source": source.value,
                    "created_by_id": actor_id if source == VersionSource.HUMAN else None,
                    "change_summary": change_summary,
                },
            )
        return new_version


def restore_version(
    session: Session,
    target_version_id: UUID,
    actor: Any,
    reason: str | None = None,
) -> ContentVersion:
    target = session.get(ContentVersion, target_version_id)
    if target is None:
        raise ValueError("Target version not found")

    restored = update_content(
        session=session,
        lesson_id=target.lesson_id,
        content_type=ContentType(target.content_type),
        new_content=target.content,
        actor=actor,
        source=VersionSource.RESTORE,
        change_summary=reason,
        emit_created_audit=False,
    )
    tx_ctx = nullcontext() if session.in_transaction() else session.begin()
    with tx_ctx:
        restored.restored_from_id = target.id
        session.add(restored)
        log_event(
            session=session,
            actor=actor,
            entity_type="lesson",
            entity_id=str(target.lesson_id),
            action=f"{target.content_type}.restored",
            payload={
                "restored_version_id": str(restored.id),
                "restored_from_id": str(target.id),
                "lesson_id": target.lesson_id,
                "content_type": target.content_type,
                "reason": reason,
            },
        )
    return restored


def list_versions(
    session: Session,
    lesson_id: int,
    content_type: ContentType,
    limit: int = 50,
    before: Optional[int] = None,
) -> list[ContentVersion]:
    statement = (
        select(ContentVersion)
        .where(
            ContentVersion.lesson_id == lesson_id,
            ContentVersion.content_type == content_type.value,
        )
        .options(
            load_only(
                ContentVersion.id,
                ContentVersion.lesson_id,
                ContentVersion.content_type,
                ContentVersion.version_number,
                ContentVersion.version_source,
                ContentVersion.created_at,
                ContentVersion.last_edited_at,
                ContentVersion.edit_count,
                ContentVersion.is_sealed,
                ContentVersion.sealed_at,
                ContentVersion.sealed_reason,
                ContentVersion.created_by_id,
                ContentVersion.change_summary,
                ContentVersion.parent_version_id,
                ContentVersion.restored_from_id,
                ContentVersion.is_current,
            )
        )
        .order_by(ContentVersion.version_number.desc())
        .limit(limit)
    )
    if before is not None:
        statement = statement.where(ContentVersion.version_number < before)
    return list(session.exec(statement).all())


def get_version(session: Session, version_id: UUID) -> ContentVersion:
    row = session.get(ContentVersion, version_id)
    if row is None:
        raise ValueError("Version not found")
    return row


def compute_diff(version_a: ContentVersion, version_b: ContentVersion) -> dict[str, Any]:
    content_type = ContentType(version_a.content_type)
    if version_b.content_type != version_a.content_type:
        raise ValueError("Cannot diff different content types")

    if content_type in (ContentType.TITLE, ContentType.BRIEF, ContentType.SUMMARY):
        a_text = str(version_a.content or "")
        b_text = str(version_b.content or "")
        lines = list(
            unified_diff(
                a_text.splitlines(),
                b_text.splitlines(),
                fromfile=f"v{version_a.version_number}",
                tofile=f"v{version_b.version_number}",
                lineterm="",
            )
        )
        return {"type": "text", "diff": "\n".join(lines)}

    left = version_a.content or []
    right = version_b.content or []
    max_len = max(len(left), len(right))
    items: list[dict[str, Any]] = []
    for idx in range(max_len):
        if idx >= len(left):
            items.append({"segment_index": idx, "status": "added", "text_diff": str(right[idx].get("text", ""))})
            continue
        if idx >= len(right):
            items.append({"segment_index": idx, "status": "removed", "text_diff": str(left[idx].get("text", ""))})
            continue
        left_text = str(left[idx].get("text", ""))
        right_text = str(right[idx].get("text", ""))
        if left_text == right_text:
            items.append({"segment_index": idx, "status": "unchanged", "text_diff": ""})
            continue
        lines = list(
            unified_diff(
                left_text.splitlines(),
                right_text.splitlines(),
                fromfile=f"{idx}:a",
                tofile=f"{idx}:b",
                lineterm="",
            )
        )
        items.append(
            {
                "segment_index": idx,
                "status": "modified",
                "text_diff": "\n".join(lines),
            }
        )
    return {"type": "structured", "segments": items}
