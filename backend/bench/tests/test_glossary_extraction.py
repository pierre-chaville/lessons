"""Correction step: extraction of the new Hebrew terms into the app glossary (as the app does in
native Hebrew mode), without merging the output segments."""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import database
from bench import steps
from bench.dataset import LessonItem
from bench.run import CACHE_NEUTRAL_PARAMS
from models.glossary import GlossaryEntry

INPUT = "- [0s - 2s] le verset dit\n- [2s - 4s] et c'est tout\n"
CORRECTED = ["le verset dit אֵין עוֹד", "מִלְבַדּוֹ, et c'est <d alt=\"x\">תְּשׁוּבָה</d>"]


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    return engine


class FakeLLM:
    pass


def correct(monkeypatch, **params) -> dict:
    async def fake_correct(segments, llm, prompt, segments_per_group, max_concurrency):
        return CORRECTED

    monkeypatch.setattr(steps, "_build_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(steps, "_correct_segments", fake_correct)
    item = LessonItem("x", "extracts", None, meta={"lesson_id": "Ae6G85zd"})
    return steps.correction(INPUT, item=item, provider="openai", model="m", prompt="p",
                            params={"glossary": False, **params}, timeout=10)


def test_new_terms_are_added_with_their_merged_context(monkeypatch, engine):
    result = correct(monkeypatch, extract_glossary=True)
    assert result["output"].count("\n") == 2  # segments not merged in the output
    assert result["meta"]["new_glossary_entries"] == ["אֵין עוֹד מִלְבַדּוֹ", "תְּשׁוּבָה"]
    with Session(engine) as session:
        entries = session.exec(select(GlossaryEntry)).all()
    assert {(e.status, e.context_lesson) for e in entries} == {("auto", "Ae6G85zd")}
    assert entries[0].context_paragraph == "le verset dit אֵין עוֹד מִלְבַדּוֹ, et c'est תְּשׁוּבָה"
    assert correct(monkeypatch, extract_glossary=True)["meta"]["new_glossary_entries"] == []  # already there


def test_off_by_default(monkeypatch, engine):
    assert "new_glossary_entries" not in correct(monkeypatch)["meta"]
    with Session(engine) as session:
        assert session.exec(select(GlossaryEntry)).all() == []


def test_not_in_the_cache_key():
    assert "extract_glossary" in CACHE_NEUTRAL_PARAMS
