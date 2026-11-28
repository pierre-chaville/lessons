"""Integration tests for theme JSON export / import (SQLite, auth overridden)."""

from collections.abc import Iterator

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import auth
import crud
import database
from models.theme import Theme
from routers import themes as themes_router


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _client(session: Session, role: str = "admin") -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(themes_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "user_1", "role": role}
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_export_is_a_name_based_tree(session: Session) -> None:
    root = crud.create_theme(session, "Fêtes", description="Calendrier")
    crud.create_theme(session, "Pessa'h", parent_id=root.id)
    crud.create_theme(session, "Souccot", parent_id=root.id)
    crud.create_theme(session, "Moussar")

    async with _client(session, role="reader") as client:
        response = await client.get("/themes/export")

    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "themes"
    assert body["version"] == 1
    assert body["themes"] == [
        {
            "name": "Fêtes",
            "description": "Calendrier",
            "children": [
                {"name": "Pessa'h", "description": None, "children": []},
                {"name": "Souccot", "description": None, "children": []},
            ],
        },
        {"name": "Moussar", "description": None, "children": []},
    ]


@pytest.mark.anyio
async def test_import_merges_by_name_under_same_parent(session: Session) -> None:
    root = crud.create_theme(session, "Fêtes", description="Old")
    crud.create_theme(session, "Pessa'h", parent_id=root.id)

    payload = {
        "format": "themes",
        "version": 1,
        "exported_at": "2026-01-01T00:00:00Z",
        "themes": [
            {
                "name": " fêtes ",  # case/whitespace-insensitive match
                "description": "New",
                "children": [
                    {"name": "Pessa'h"},  # no description key → left unchanged
                    {"name": "Chavouot", "children": [{"name": "Matan Torah"}]},
                ],
            },
            {"name": "Pessa'h"},  # same name at root level is a different theme
        ],
    }
    async with _client(session) as client:
        response = await client.post("/themes/import", json=payload)

    assert response.status_code == 200
    assert response.json() == {"created": 3, "updated": 1, "unchanged": 1, "total": 5}

    themes = {(t.name, t.parent_id): t for t in session.exec(select(Theme)).all()}
    assert themes[("Fêtes", None)].description == "New"
    chavouot = themes[("Chavouot", root.id)]
    assert chavouot.sort_order == 1
    assert ("Matan Torah", chavouot.id) in themes
    assert ("Pessa'h", None) in themes


@pytest.mark.anyio
async def test_export_then_import_is_idempotent(session: Session) -> None:
    root = crud.create_theme(session, "A")
    crud.create_theme(session, "B", parent_id=root.id)
    async with _client(session) as client:
        exported = (await client.get("/themes/export")).json()
        result = (await client.post("/themes/import", json=exported)).json()
    assert result == {"created": 0, "updated": 0, "unchanged": 2, "total": 2}
    assert len(session.exec(select(Theme)).all()) == 2


@pytest.mark.anyio
async def test_import_rejects_empty_name_and_writes_nothing(session: Session) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/themes/import", json={"themes": [{"name": "Ok", "children": [{"name": "  "}]}]}
        )
    assert response.status_code == 422
    assert session.exec(select(Theme)).all() == []


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["reader", "editor"])
async def test_import_requires_publisher_or_admin(session: Session, role: str) -> None:
    async with _client(session, role=role) as client:
        response = await client.post("/themes/import", json={"themes": [{"name": "X"}]})
    assert response.status_code == 403
