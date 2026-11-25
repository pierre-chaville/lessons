"""Tests for /me/preferences (own Hebrew display settings)."""

from collections.abc import Iterator

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import auth
import database
from models import UserPreference
from routers import me as me_router

SETTINGS = {
    "primary": "vocalized",
    "supplement": "translation",
    "frequency": "every",
    "quotations_in_hebrew": False,
}


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _client(session: Session, role: str = "reader", sub: str | None = "user_1") -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(me_router.router)
    claims = {"role": role} if sub is None else {"sub": sub, "role": role}
    app.dependency_overrides[auth.require_auth] = lambda: claims
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_preferences_default_then_saved_per_user(session) -> None:
    async with _client(session) as client:
        initial = await client.get("/me/preferences")
        saved = await client.put("/me/preferences/hebrew-display", json=SETTINGS)
        reloaded = await client.get("/me/preferences")
    async with _client(session, sub="user_2") as other:
        other_user = await other.get("/me/preferences")

    assert initial.status_code == 200 and initial.json() == {"hebrew_display": None}
    assert saved.status_code == 200 and saved.json() == SETTINGS
    assert reloaded.json() == {"hebrew_display": SETTINGS}
    assert other_user.json() == {"hebrew_display": None}


@pytest.mark.anyio
async def test_update_replaces_existing_settings(session) -> None:
    async with _client(session, role="admin") as client:
        await client.put("/me/preferences/hebrew-display", json=SETTINGS)
        changed = {**SETTINGS, "primary": "translit", "supplement": "none"}
        await client.put("/me/preferences/hebrew-display", json=changed)
        reloaded = await client.get("/me/preferences")
    assert reloaded.json() == {"hebrew_display": changed}
    assert len(session.exec(select(UserPreference)).all()) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {**SETTINGS, "primary": "hebrew"},
        {key: value for key, value in SETTINGS.items() if key != "frequency"},
        {**SETTINGS, "user_id": "user_2"},
    ],
)
async def test_invalid_settings_are_rejected(session, payload) -> None:
    async with _client(session) as client:
        response = await client.put("/me/preferences/hebrew-display", json=payload)
    assert response.status_code == 422


@pytest.mark.anyio
async def test_access_requires_role_and_user_id(session) -> None:
    async with _client(session, role="") as no_role:
        denied = await no_role.get("/me/preferences")
    async with _client(session, sub=None) as no_sub:
        anonymous = await no_sub.put("/me/preferences/hebrew-display", json=SETTINGS)
    assert denied.status_code == 403
    assert anonymous.status_code == 403


@pytest.mark.anyio
async def test_invalid_stored_settings_fall_back_to_defaults(session) -> None:
    session.add(UserPreference(user_id="user_1", hebrew_display={"primary": "old-mode"}))
    session.commit()
    async with _client(session) as client:
        response = await client.get("/me/preferences")
    assert response.json() == {"hebrew_display": None}
