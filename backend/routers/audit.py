"""Global audit log router."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from auth import require_roles
from database import get_session
from schemas.lesson import AuditLogResponse
from services.audit import AuditLogFilters, query_audit_log

router = APIRouter(tags=["Audit"])


@router.get("/audit-log", response_model=List[AuditLogResponse])
def get_global_audit_log(
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    occurred_after: Optional[datetime] = Query(None),
    occurred_before: Optional[datetime] = Query(None),
    limit: int = Query(100, le=500),
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    rows = query_audit_log(
        session,
        AuditLogFilters(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            limit=limit,
        ),
    )
    return [AuditLogResponse.model_validate(row) for row in rows]
