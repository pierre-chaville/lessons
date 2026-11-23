"""Startup migration: transliteration glossary moves to glossary_legacy_entry."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

import database


def test_old_glossary_table_becomes_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE glossary_entry (id INTEGER PRIMARY KEY, standard VARCHAR NOT NULL, "
            "variations JSON NOT NULL, exact_case BOOLEAN NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO glossary_entry (standard, variations, exact_case) "
            "VALUES ('techouva', '[\"tchouva\"]', 0)"
        ))
    # Startup order: create_all() first (creates an empty legacy table), then migrations.
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    database._migrate_legacy_glossary_table()
    database._migrate_legacy_glossary_table()  # idempotent

    inspector = inspect(engine)
    new_columns = {col["name"] for col in inspector.get_columns("glossary_entry")}
    assert {"hebrew", "hebrew_norm", "hebrew_cons"} <= new_columns
    assert "standard" not in new_columns
    with engine.connect() as conn:
        legacy = conn.execute(text("SELECT standard FROM glossary_legacy_entry")).scalars().all()
        new_rows = conn.execute(text("SELECT COUNT(*) FROM glossary_entry")).scalar()
    assert legacy == ["techouva"]
    assert new_rows == 0
