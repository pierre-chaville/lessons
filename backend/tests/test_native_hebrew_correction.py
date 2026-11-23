"""Post-correction steps for native-Hebrew transcripts: merge and glossary feed."""

from collections.abc import Iterator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import crud
from hashid_utils import encode_id
from hebrew_text import extract_hebrew_expressions, merge_hebrew_segments
from models.glossary import GlossaryEntry
from services.correction import _process_native_hebrew

TESHUVA = "תְּשׁוּבָה"
EIN_OD = "אֵין עוֹד מִלְבַדּוֹ"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


def test_merge_joins_segments_across_hebrew_boundary() -> None:
    segments = [
        _seg(0, 1, "Le verset dit אֵין עוֹד"),
        _seg(1, 2, "מִלְבַדּוֹ, et c'est"),
        _seg(2, 3, "fondamental."),
    ]
    assert merge_hebrew_segments(segments) == [
        _seg(0, 2, "Le verset dit אֵין עוֹד מִלְבַדּוֹ, et c'est"),
        _seg(2, 3, "fondamental."),
    ]


def test_merge_chains_over_several_segments_and_ignores_punctuation() -> None:
    segments = [
        _seg(0, 1, "« בְּרֵאשִׁית"),
        _seg(1, 2, "בָּרָא"),
        _seg(2, 3, "אֱלֹהִים »"),
        _seg(3, 4, "dit le texte"),
    ]
    merged = merge_hebrew_segments(segments)
    assert [(s["start"], s["end"]) for s in merged] == [(0, 3), (3, 4)]
    assert merged[0]["text"] == "« בְּרֵאשִׁית בָּרָא אֱלֹהִים »"


def test_merge_keeps_segments_when_one_side_is_not_hebrew() -> None:
    segments = [_seg(0, 1, f"la {TESHUVA}"), _seg(1, 2, f"et la {TESHUVA}")]
    assert merge_hebrew_segments(segments) == segments


def test_extract_expressions_runs_trimming_and_dedup() -> None:
    text = f"La {TESHUVA}, puis « {EIN_OD} », encore {TESHUVA} et רש\"י וכו'."
    assert extract_hebrew_expressions(text) == [TESHUVA, EIN_OD, 'רש"י וכו\'']


def test_extract_ignores_text_without_hebrew() -> None:
    assert extract_hebrew_expressions("Aucun mot hébreu ici.") == []


def test_add_missing_entries_skips_existing_and_duplicate_keys(session: Session) -> None:
    crud.create_glossary_entry(session, {"hebrew": TESHUVA, "translit": "techouva"})
    created = crud.add_missing_glossary_entries(
        session,
        [
            {"hebrew": TESHUVA},
            {"hebrew": EIN_OD, "context_paragraph": "first"},
            {"hebrew": f"  {EIN_OD} ", "context_paragraph": "second"},
        ],
        status="auto",
        source="llm",
    )
    assert [entry.hebrew_norm for entry in created] == [EIN_OD]
    assert created[0].context_paragraph == "first"
    existing = crud.get_glossary_entry_by_hebrew_norm(session, TESHUVA)
    assert existing.translit == "techouva"
    assert existing.source == "manual"


def test_process_native_hebrew_merges_and_feeds_glossary(session: Session) -> None:
    crud.create_glossary_entry(session, {"hebrew": TESHUVA})
    segments = [
        _seg(0, 1, f"La {TESHUVA} et אֵין עוֹד"),
        _seg(1, 2, "מִלְבַדּוֹ selon le verset."),
    ]
    merged, report = _process_native_hebrew(session, 7, segments)

    assert merged == [_seg(0, 2, f"La {TESHUVA} et {EIN_OD} selon le verset.")]
    assert report == {
        "segments_before_merge": 2,
        "segments_after_merge": 1,
        "new_glossary_entries": 1,
    }
    entries = session.exec(select(GlossaryEntry).order_by(GlossaryEntry.id)).all()
    assert len(entries) == 2
    new_entry = entries[1]
    assert new_entry.hebrew == EIN_OD
    assert (new_entry.status, new_entry.source, new_entry.type) == ("auto", "llm", "term")
    assert new_entry.translit is None and new_entry.translation is None
    assert new_entry.aliases == []
    assert new_entry.context_lesson == encode_id(7)
    assert new_entry.context_paragraph == merged[0]["text"]
