"""Tests for GET /lessons/{id}/hebrew-terms and hebrew_lookup_keys."""

from collections.abc import Iterator

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import auth
import crud
import database
from hashid_utils import encode_id
from hebrew_text import hebrew_consonants, hebrew_lookup_keys
from models import Lesson
from routers import lessons as lessons_router

TESHUVA = "תְּשׁוּבָה"
EIN_OD = "אֵין עוֹד מִלְבַדּוֹ"
SHABBAT = "שַׁבָּת"
HESSED = "חֶסֶד"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _client(session: Session, role: str) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(lessons_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "user_1", "role": role}
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _lesson(session: Session, **values) -> Lesson:
    lesson = Lesson(title="L", filename="l.mp3", **values)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def test_lookup_keys_cover_sub_expressions_and_ignore_tags() -> None:
    text = f'La **{TESHUVA}** et <d alt="{HESSED}">{EIN_OD}</d>, fin.'
    norms, consonants = hebrew_lookup_keys(text)
    assert TESHUVA in norms and EIN_OD in norms and "אֵין עוֹד" in norms and "מִלְבַדּוֹ" in norms
    assert hebrew_consonants(EIN_OD) in consonants
    # Hebrew only present in a tag attribute is not a lesson term.
    assert HESSED not in norms
    # Runs are broken by non-Hebrew words: no key spans "תשובה et אין".
    assert not any(TESHUVA in key and "אֵין" in key for key in norms)


@pytest.mark.anyio
async def test_hebrew_terms_endpoint_returns_matching_entries_to_readers(session) -> None:
    teshuva = crud.create_glossary_entry(
        session,
        {"hebrew": TESHUVA, "translit": "techouva", "translation": "repentir", "status": "validated"},
    )
    ein_od = crud.create_glossary_entry(session, {"hebrew": EIN_OD, "status": "auto", "type": "quotation"})
    crud.create_glossary_entry(session, {"hebrew": SHABBAT, "translit": "chabbat"})  # not in the lesson
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "rejected"})
    lesson = _lesson(
        session,
        summary=f"Résumé : la תשובה et le {HESSED}.",  # unvocalized: matched by consonants
        summary_hebrew_mode="native",
        edited_transcript={"markdown": f"Il dit {EIN_OD}."},
        edited_transcript_hebrew_mode="partial",
    )

    async with _client(session, "reader") as client:
        response = await client.get(f"/lessons/{encode_id(lesson.id)}/hebrew-terms")

    assert response.status_code == 200
    terms = {term["id"]: term for term in response.json()}
    assert set(terms) == {teshuva.id, ein_od.id}
    assert terms[teshuva.id]["translit"] == "techouva"
    assert terms[teshuva.id]["validated"] is True
    assert terms[ein_od.id]["type"] == "quotation" and terms[ein_od.id]["validated"] is False


@pytest.mark.anyio
async def test_translit_texts_are_skipped_and_missing_lesson_is_404(session) -> None:
    crud.create_glossary_entry(session, {"hebrew": TESHUVA, "translit": "techouva"})
    lesson = _lesson(session, summary=f"la {TESHUVA}", summary_hebrew_mode="translit")
    async with _client(session, "reader") as client:
        skipped = await client.get(f"/lessons/{encode_id(lesson.id)}/hebrew-terms")
        missing = await client.get(f"/lessons/{encode_id(9999)}/hebrew-terms")
    assert skipped.json() == []
    assert missing.status_code == 404
