"""Audit log model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _jsonb_column() -> Column:
    """Use JSONB on PostgreSQL and JSON elsewhere (tests/dev sqlite)."""
    return Column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )


class AuditLog(SQLModel, table=True):
    """Append-only event log for auditable actions."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index(
            "ix_audit_entity_timeline",
            "entity_type",
            "entity_id",
            "occurred_at",
        ),
    )

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger().with_variant(Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
    )
    occurred_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime, nullable=False, index=True),
    )
    actor_id: Optional[str] = Field(default=None, index=True)
    actor_role: str = Field(sa_column=Column(String, nullable=False))
    entity_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    # str by design because audited entities use mixed key types (int, UUID, etc.).
    entity_id: str = Field(sa_column=Column(String, nullable=False, index=True))
    action: str = Field(sa_column=Column(String, nullable=False, index=True))
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb_column())
