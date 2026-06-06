from __future__ import annotations

from datetime import datetime

from sqlmodel import SQLModel, Session, create_engine

from models.lesson import Lesson
from models.versioning import ContentType, VersionSource
from services import rag_embeddings
from services.rag_embeddings import compute_rag_hash, recompute_current_rag_hashes
from services.versioning import update_content


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


def test_update_content_marks_summary_rag_hash_current() -> None:
    model = rag_embeddings.rag_embedding_model_from_config()

    with _session() as session:
        lesson = _lesson(session, "first", "")

        update_content(
            session=session,
            lesson_id=lesson.id,
            content_type=ContentType.SUMMARY,
            new_content="Fresh summary",
            actor={"sub": "u1", "role": "editor"},
            source=VersionSource.HUMAN,
        )
        session.commit()
        session.refresh(lesson)

        assert lesson.rag_summary_current_hash == compute_rag_hash(
            "Fresh summary",
            model,
        )
        assert lesson.rag_summary_stored_hash is None


def test_rebuild_stale_rag_embeddings_does_not_recompute_all_hashes(monkeypatch) -> None:
    with _session() as session:
        _lesson(session, "first", "")

        monkeypatch.setattr(
            rag_embeddings,
            "recompute_current_rag_hashes",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected recompute")),
        )

        stats = rag_embeddings.rebuild_stale_rag_embeddings(session)

        assert stats == {
            "stale_lessons": 0,
            "processed_variants": 0,
            "chunks_written": 0,
            "failed_variants": 0,
        }
