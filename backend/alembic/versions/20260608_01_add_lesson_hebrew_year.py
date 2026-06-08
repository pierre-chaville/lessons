"""add lesson hebrew year

Revision ID: 20260608_01
Revises: 20260607_01
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from convertdate import hebrew
from datetime import datetime


revision = "20260608_01"
down_revision = "20260607_01"
branch_labels = None
depends_on = None


def _hebrew_year_from_datetime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    year, _month, _day = hebrew.from_gregorian(value.year, value.month, value.day)
    return str(year)


def upgrade() -> None:
    op.add_column("lesson", sa.Column("hebrew_year", sa.String(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, date FROM lesson")).mappings().all()
    for row in rows:
        hebrew_year = _hebrew_year_from_datetime(row["date"])
        if hebrew_year:
            bind.execute(
                sa.text("UPDATE lesson SET hebrew_year = :hebrew_year WHERE id = :id"),
                {"hebrew_year": hebrew_year, "id": row["id"]},
            )


def downgrade() -> None:
    op.drop_column("lesson", "hebrew_year")
