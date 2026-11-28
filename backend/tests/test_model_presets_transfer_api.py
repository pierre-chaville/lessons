"""Integration tests for model preset JSON export / import (SQLite, auth overridden)."""

from collections.abc import Iterator

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import auth
import crud
import database
from models.model_preset import ModelPreset
from routers import model_presets as model_presets_router


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
    app.include_router(model_presets_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "user_1", "role": role}
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _preset(preset_id: int, name: str, **overrides: object) -> dict:
    return {
        "id": preset_id,
        "name": name,
        "provider": "anthropic",
        "model_id": "claude-sonnet",
        "temperature": 0.2,
        "cost_input_per_m_tokens": 3.0,
        "cost_output_per_m_tokens": 15.0,
        "flex_cost_ratio": 0.5,
        "thinking_mode": {},
        **overrides,
    }


@pytest.mark.anyio
async def test_export_keeps_ids_and_omits_timestamps(session: Session) -> None:
    crud.create_model_preset(session, name="A", provider="openai", model_id="gpt", thinking_mode={"effort": "high"})
    async with _client(session, role="publisher") as client:
        response = await client.get("/model-presets/export")
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "model_presets"
    [preset] = body["presets"]
    assert preset["id"] == 1
    assert preset["thinking_mode"] == {"effort": "high"}
    assert "created_at" not in preset


@pytest.mark.anyio
async def test_import_upserts_by_id(session: Session) -> None:
    crud.create_model_preset(session, name="Same", provider="anthropic", model_id="claude-sonnet",
                             temperature=0.2, cost_input_per_m_tokens=3.0, cost_output_per_m_tokens=15.0)
    crud.create_model_preset(session, name="Old", provider="openai", model_id="gpt")
    crud.create_model_preset(session, name="Untouched", provider="openai", model_id="gpt")

    payload = {"presets": [_preset(1, "Same"), _preset(2, "New name"), _preset(7, "Created")]}
    async with _client(session) as client:
        response = await client.post("/model-presets/import", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "created": 1, "updated": 1, "unchanged": 1, "total": 3, "ids_not_in_file": [3],
    }
    by_id = {p.id: p for p in session.exec(select(ModelPreset)).all()}
    assert by_id[2].name == "New name" and by_id[2].provider == "anthropic"
    assert by_id[7].name == "Created"
    assert by_id[3].name == "Untouched"

    # Later manual creation does not collide with the imported id.
    created = crud.create_model_preset(session, name="Next", provider="openai", model_id="gpt")
    assert created.id == 8


@pytest.mark.anyio
async def test_export_then_import_is_idempotent(session: Session) -> None:
    crud.create_model_preset(session, name="A", provider="openai", model_id="gpt")
    async with _client(session) as client:
        exported = (await client.get("/model-presets/export")).json()
        result = (await client.post("/model-presets/import", json=exported)).json()
    assert result["unchanged"] == 1 and result["created"] == 0 and result["updated"] == 0


@pytest.mark.anyio
async def test_import_rejects_duplicate_ids(session: Session) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/model-presets/import", json={"presets": [_preset(1, "A"), _preset(1, "B")]}
        )
    assert response.status_code == 422
    assert session.exec(select(ModelPreset)).all() == []


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["reader", "editor", "publisher"])
async def test_import_requires_admin(session: Session, role: str) -> None:
    async with _client(session, role=role) as client:
        response = await client.post("/model-presets/import", json={"presets": [_preset(1, "A")]})
    assert response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["reader", "editor"])
async def test_export_requires_publisher_or_admin(session: Session, role: str) -> None:
    async with _client(session, role=role) as client:
        assert (await client.get("/model-presets/export")).status_code == 403
