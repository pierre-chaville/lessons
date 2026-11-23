"""Integration tests for the Hebrew-keyed glossary API (SQLite, auth overridden)."""

from collections.abc import Iterator

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
import yaml

import auth
import database
from models.glossary import LegacyGlossaryEntry
from routers import glossary as glossary_router

TESHUVA = "תְּשׁוּבָה"


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
    app.include_router(glossary_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "user_1", "role": role}
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_create_computes_keys_and_defaults(session: Session) -> None:
    async with _client(session) as client:
        response = await client.post(
            "/glossary",
            json={"hebrew": f" {TESHUVA} ", "translit": "techouva", "aliases": ["techuva", "techuva", " "]},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["hebrew"] == TESHUVA
    assert body["hebrew_cons"] == "תשובה"
    assert body["aliases"] == ["techuva"]
    assert body["type"] == "term"
    assert body["case_flag"] == "lower"
    assert body["status"] == "validated"
    assert body["source"] == "manual"
    assert body["hashid"]


@pytest.mark.anyio
async def test_duplicate_hebrew_norm_conflicts(session: Session) -> None:
    async with _client(session) as client:
        assert (await client.post("/glossary", json={"hebrew": TESHUVA})).status_code == 201
        # Same word with a cantillation mark normalizes to the same key.
        response = await client.post("/glossary", json={"hebrew": "תְּשׁ֖וּבָה"})
    assert response.status_code == 409


@pytest.mark.anyio
async def test_rejects_non_hebrew_and_invalid_enums(session: Session) -> None:
    async with _client(session) as client:
        assert (await client.post("/glossary", json={"hebrew": "techouva"})).status_code == 422
        assert (await client.post("/glossary", json={"hebrew": TESHUVA, "type": "bogus"})).status_code == 422


@pytest.mark.anyio
async def test_list_filters_and_paginates(session: Session) -> None:
    async with _client(session) as client:
        await client.post("/glossary", json={"hebrew": TESHUVA, "translit": "techouva", "translation": "repentance"})
        await client.post("/glossary", json={"hebrew": "יוֹם כִּפּוּר", "translit": "Yom Kippour", "type": "holiday", "status": "auto"})
        await client.post("/glossary", json={"hebrew": "רַמְבַּ\"ם", "translit": "Rambam", "type": "author", "aliases": ["Maimonide"]})

        by_cons = (await client.get("/glossary", params={"q": "תשובה"})).json()
        # ASCII alias: SQLite stores JSON with non-ASCII escaped (PostgreSQL jsonb does not).
        by_alias = (await client.get("/glossary", params={"q": "maimonide"})).json()
        by_translation = (await client.get("/glossary", params={"q": "REPENT"})).json()
        by_type = (await client.get("/glossary", params={"type": "holiday"})).json()
        by_status = (await client.get("/glossary", params={"status": "auto"})).json()
        paged = (await client.get("/glossary", params={"per_page": 2, "page": 2})).json()

    assert [e["translit"] for e in by_cons["items"]] == ["techouva"]
    assert [e["translit"] for e in by_alias["items"]] == ["Rambam"]
    assert [e["translit"] for e in by_translation["items"]] == ["techouva"]
    assert [e["translit"] for e in by_type["items"]] == ["Yom Kippour"]
    assert [e["translit"] for e in by_status["items"]] == ["Yom Kippour"]
    assert paged["total"] == 3 and len(paged["items"]) == 1 and paged["page"] == 2


@pytest.mark.anyio
async def test_update_recomputes_keys_and_rejects_null(session: Session) -> None:
    async with _client(session) as client:
        created = (await client.post("/glossary", json={"hebrew": TESHUVA, "translation": "repentance"})).json()
        hashid = created["hashid"]
        updated = await client.patch(
            f"/glossary/{hashid}",
            json={"hebrew": "תְּשׁוּבוֹת", "status": "auto", "translation": None},
        )
        null_type = await client.patch(f"/glossary/{hashid}", json={"type": None})
    assert updated.status_code == 200
    assert updated.json()["hebrew_cons"] == "תשובות"
    assert updated.json()["translation"] is None
    assert updated.json()["status"] == "auto"
    assert null_type.status_code == 422


@pytest.mark.anyio
async def test_yaml_round_trip_upserts_by_hebrew_norm(session: Session) -> None:
    async with _client(session) as client:
        await client.post("/glossary", json={"hebrew": TESHUVA, "translit": "techouva"})
        exported = await client.get("/glossary/export/yaml")
        items = yaml.safe_load(exported.text)
        items[0]["translit"] = "techouvah"
        items.append({"hebrew": "חֶסֶד", "translit": "'hessed", "source": "llm", "status": "auto"})
        result = await client.post(
            "/glossary/import/yaml",
            files={"file": ("g.yaml", yaml.safe_dump(items, allow_unicode=True), "application/x-yaml")},
        )
        listing = (await client.get("/glossary")).json()
    assert result.json() == {"created": 1, "updated": 1, "total": 2}
    assert sorted(e["translit"] for e in listing["items"]) == ["'hessed", "techouvah"]


@pytest.mark.anyio
async def test_legacy_export_and_role_checks(session: Session) -> None:
    session.add(LegacyGlossaryEntry(standard="techouva", variations=["tchouva"], exact_case=False))
    session.commit()
    async with _client(session, role="editor") as editor:
        legacy = await editor.get("/glossary/legacy/export/yaml")
        listing = await editor.get("/glossary")
        create = await editor.post("/glossary", json={"hebrew": TESHUVA})
    async with _client(session, role="reader") as reader:
        reader_listing = await reader.get("/glossary")
    assert yaml.safe_load(legacy.text) == [
        {"standard": "techouva", "variations": ["tchouva"], "exactCase": False}
    ]
    assert listing.status_code == 200
    assert create.status_code == 403
    assert reader_listing.status_code == 403
