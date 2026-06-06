from __future__ import annotations

from datetime import datetime

from sqlmodel import SQLModel, Session, create_engine

from models.lesson import Lesson
from services.rag_embeddings import compute_rag_hash, recompute_current_rag_hashes


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _lesson(session: Session, title: str, summary: str) -> Lesson:
    lesson = Lesson(
        title=title,
        filename=f"{title}.mp3",
        date=datetime.utcnow(),
        transcript=[],
        edited_transcript=None,
        summary=summary,
        status="draft",
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def test_recompute_current_rag_hashes_updates_in_batches() -> None:
    model = "google/gemini-embedding-001"

    with _session() as session:
        first = _lesson(session, "first", "First summary")
        second = _lesson(session, "second", "Second summary")
        first_id = first.id
        second_id = second.id

        changed = recompute_current_rag_hashes(session, model, batch_size=1)

        assert changed == 2
        refreshed_first = session.get(Lesson, first_id)
        refreshed_second = session.get(Lesson, second_id)
        assert refreshed_first.rag_summary_current_hash == compute_rag_hash(
            "First summary",
            model,
        )
        assert refreshed_second.rag_summary_current_hash == compute_rag_hash(
            "Second summary",
            model,
        )
