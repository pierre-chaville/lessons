"""Audit service helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from models.audit import AuditLog


@dataclass
class AuditLogFilters:
    actor_id: Optional[str] = None
    action: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    occurred_after: Optional[datetime] = None
    occurred_before: Optional[datetime] = None
    limit: int = 100


def _actor_id(actor: Any) -> Optional[str]:
    if actor is None:
        return None
    if isinstance(actor, dict):
        return actor.get("sub")
    return getattr(actor, "id", None)


def _actor_role(actor: Any) -> str:
    if actor is None:
        return "system"
    if isinstance(actor, dict):
        for key in ("role", "actor_role"):
            if actor.get(key):
                return str(actor[key])
        # Clerk-style metadata fallback
        metadata = actor.get("public_metadata") or {}
        if isinstance(metadata, dict) and metadata.get("role"):
            return str(metadata["role"])
        return "unknown"
    return str(getattr(actor, "role", "unknown"))


def log_event(
    session: Session,
    actor: Any,
    entity_type: str,
    entity_id: str,
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Write one audit event with actor role snapshot."""
    row = AuditLog(
        occurred_at=datetime.utcnow(),
        actor_id=_actor_id(actor),
        actor_role=_actor_role(actor),
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        payload=payload or {},
    )
    session.add(row)
    session.flush()
    return row


def get_lesson_audit_log(
    session: Session,
    lesson_id: int,
    limit: int = 100,
    before_id: Optional[int] = None,
) -> list[AuditLog]:
    statement = (
        select(AuditLog)
        .where(AuditLog.entity_type == "lesson", AuditLog.entity_id == str(lesson_id))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        statement = statement.where(AuditLog.id < before_id)
    return list(session.exec(statement).all())


def query_audit_log(
    session: Session,
    filters: AuditLogFilters,
) -> list[AuditLog]:
    statement = select(AuditLog)
    if filters.actor_id:
        statement = statement.where(AuditLog.actor_id == filters.actor_id)
    if filters.action:
        statement = statement.where(AuditLog.action == filters.action)
    if filters.entity_type:
        statement = statement.where(AuditLog.entity_type == filters.entity_type)
    if filters.entity_id:
        statement = statement.where(AuditLog.entity_id == filters.entity_id)
    if filters.occurred_after:
        statement = statement.where(AuditLog.occurred_at >= filters.occurred_after)
    if filters.occurred_before:
        statement = statement.where(AuditLog.occurred_at <= filters.occurred_before)
    statement = statement.order_by(AuditLog.id.desc()).limit(filters.limit)
    return list(session.exec(statement).all())
