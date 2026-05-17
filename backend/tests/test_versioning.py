"""Unit tests for lesson content versioning/audit behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
import json

from sqlmodel import Session, SQLModel, create_engine, select

from models.audit import AuditLog
from models.lesson import Lesson
from models.versioning import ContentType, ContentVersion, VersionSource
from services.lessons import change_status
from services.versioning import compute_diff, seal_current_version, update_content, restore_version


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _lesson(session: Session) -> Lesson:
    lesson = Lesson(
        title="Initial",
        filename="file.mp3",
        date=datetime.utcnow(),
        transcript=[],
        status="draft",
    )
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def _count_audit(session: Session) -> int:
    return len(list(session.exec(select(AuditLog)).all()))


def test_first_version_created() -> None:
    with _session() as session:
        lesson = _lesson(session)
        row = update_content(
            session,
            lesson.id,
            ContentType.SUMMARY,
            "v1",
            actor={"sub": "u1", "role": "editor"},
            source=VersionSource.HUMAN,
        )
        session.commit()
        assert row.is_current is True
        assert row.version_number == 1
        assert row.edit_count == 1
        assert row.is_sealed is False


def test_update_creates_new_version_and_demotes_old() -> None:
    with _session() as session:
        lesson = _lesson(session)
        first = update_content(session, lesson.id, ContentType.SUMMARY, "a", {"sub": "u1", "role": "editor"})
        session.commit()
        second = update_content(session, lesson.id, ContentType.SUMMARY, "b", {"sub": "u1", "role": "editor"}, coalesce_window_minutes=0)
        session.commit()
        assert second.version_number == 2
        session.refresh(first)
        assert first.is_current is False
        assert second.is_current is True


def test_structurally_identical_noop() -> None:
    with _session() as session:
        lesson = _lesson(session)
        transcript = [{"start": 0.0, "end": 1.0, "text": "hello"}]
        first = update_content(session, lesson.id, ContentType.CORRECTED_TRANSCRIPT, transcript, {"sub": "u1", "role": "editor"})
        session.commit()
        audits_before = _count_audit(session)
        second = update_content(
            session,
            lesson.id,
            ContentType.CORRECTED_TRANSCRIPT,
            [{"end": 1.0, "start": 0.0, "text": "hello"}],
            {"sub": "u1", "role": "editor"},
        )
        session.commit()
        assert first.id == second.id
        assert _count_audit(session) == audits_before


def test_coalescing_same_user() -> None:
    with _session() as session:
        lesson = _lesson(session)
        first = update_content(session, lesson.id, ContentType.SUMMARY, "a", {"sub": "u1", "role": "editor"})
        session.commit()
        audits_before = _count_audit(session)
        second = update_content(session, lesson.id, ContentType.SUMMARY, "b", {"sub": "u1", "role": "editor"})
        session.commit()
        assert first.id == second.id
        assert second.version_number == 1
        assert second.edit_count == 2
        assert _count_audit(session) == audits_before


def test_different_user_takeover_seals_then_creates() -> None:
    with _session() as session:
        lesson = _lesson(session)
        first = update_content(session, lesson.id, ContentType.BRIEF, "a", {"sub": "user-a", "role": "editor"})
        session.commit()
        second = update_content(session, lesson.id, ContentType.BRIEF, "b", {"sub": "user-b", "role": "editor"})
        session.commit()
        session.refresh(first)
        assert second.version_number == 2
        assert first.is_sealed is True
        assert first.sealed_reason == "different_user"


def test_window_expiration_creates_new_version() -> None:
    with _session() as session:
        lesson = _lesson(session)
        first = update_content(session, lesson.id, ContentType.SUMMARY, "a", {"sub": "u1", "role": "editor"})
        session.commit()
        first.last_edited_at = datetime.utcnow() - timedelta(minutes=30)
        session.add(first)
        session.commit()
        second = update_content(
            session,
            lesson.id,
            ContentType.SUMMARY,
            "b",
            {"sub": "u1", "role": "editor"},
            coalesce_window_minutes=10,
        )
        session.commit()
        session.refresh(first)
        assert second.version_number == 2
        assert first.sealed_reason == "window_expired"


def test_status_transition_seals_current_versions() -> None:
    with _session() as session:
        lesson = _lesson(session)
        row = update_content(session, lesson.id, ContentType.SUMMARY, "a", {"sub": "u1", "role": "editor"})
        session.commit()
        lesson = change_status(session, lesson, "in_progress", {"sub": "u1", "role": "editor"})
        session.refresh(row)
        assert row.is_sealed is True
        assert row.sealed_reason == "status_changed"
        assert lesson.status == "in_progress"


def test_manual_checkpoint_then_new_save_creates_new_version() -> None:
    with _session() as session:
        lesson = _lesson(session)
        first = update_content(session, lesson.id, ContentType.SUMMARY, "a", {"sub": "u1", "role": "editor"})
        session.commit()
        seal_current_version(session, lesson.id, ContentType.SUMMARY, "manual_checkpoint", {"sub": "u1", "role": "editor"})
        session.commit()
        second = update_content(session, lesson.id, ContentType.SUMMARY, "b", {"sub": "u1", "role": "editor"})
        session.commit()
        assert second.version_number == 2
        session.refresh(first)
        assert first.sealed_reason == "manual_checkpoint"


def test_restore_creates_new_version_from_old() -> None:
    with _session() as session:
        lesson = _lesson(session)
        v1 = update_content(session, lesson.id, ContentType.SUMMARY, "v1", {"sub": "u1", "role": "editor"})
        session.commit()
        v2 = update_content(session, lesson.id, ContentType.SUMMARY, "v2", {"sub": "u1", "role": "editor"}, coalesce_window_minutes=0)
        session.commit()
        restored = restore_version(session, v1.id, {"sub": "u1", "role": "editor"}, reason="rollback")
        session.commit()
        assert restored.version_source == VersionSource.RESTORE.value
        assert restored.created_by_id == "u1"
        assert restored.restored_from_id == v1.id
        assert restored.version_number == 3
        session.refresh(v2)
        assert v2.sealed_reason == "restored_over"


def test_pipeline_update_handles_legacy_string_edited_transcript() -> None:
    with _session() as session:
        lesson = _lesson(session)
        legacy_payload = json.dumps([{"start": 0.0, "end": 1.0, "text": "old", "sources": []}])
        legacy = ContentVersion(
            lesson_id=lesson.id,
            content_type=ContentType.EDITED_TRANSCRIPT.value,
            content=legacy_payload,
            version_number=1,
            version_source=VersionSource.PIPELINE.value,
            created_at=datetime.utcnow(),
            last_edited_at=None,
            edit_count=1,
            is_sealed=False,
            created_by_id=None,
            change_summary="legacy payload",
            parent_version_id=None,
            is_current=True,
        )
        session.add(legacy)
        session.commit()

        updated = update_content(
            session=session,
            lesson_id=lesson.id,
            content_type=ContentType.EDITED_TRANSCRIPT,
            new_content={
                "markdown": "new",
                "sources": [[]],
                "alignment": [
                    {"start": 0.0, "end": 1.0, "match_score": 1.0, "start_index": 0, "end_index": 0}
                ],
                "transcript_hash": "abc",
                "markdown_hash": "def",
                "aligned_at": datetime.utcnow().isoformat(),
            },
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="pipeline rerun",
        )
        session.commit()

        session.refresh(legacy)
        assert legacy.is_sealed is True
        assert legacy.sealed_reason == "pipeline_rerun"
        assert updated.version_number == 2
        assert updated.is_current is True
        assert isinstance(updated.content, dict)
        assert updated.content["markdown"] == "new"


def test_update_content_strips_nul_bytes_from_edited_transcript() -> None:
    with _session() as session:
        lesson = _lesson(session)
        updated = update_content(
            session=session,
            lesson_id=lesson.id,
            content_type=ContentType.EDITED_TRANSCRIPT,
            new_content={
                "markdown": "abc\x00def",
                "sources": [[]],
                "alignment": [
                    {"start": 0.0, "end": 1.0, "match_score": 1.0, "start_index": 0, "end_index": 0}
                ],
                "transcript_hash": None,
                "markdown_hash": None,
                "aligned_at": None,
            },
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="sanitize nul bytes",
        )
        session.commit()

        assert updated.content["markdown"] == "abcdef"
        session.refresh(lesson)
        assert lesson.edited_transcript["markdown"] == "abcdef"


def test_compute_diff_summary_ignores_blank_line_only_changes() -> None:
    version_a = ContentVersion(
        lesson_id=1,
        content_type=ContentType.SUMMARY.value,
        content="# Title\nParagraph one.\nParagraph two.",
        version_number=1,
        version_source=VersionSource.HUMAN.value,
        created_at=datetime.utcnow(),
        last_edited_at=None,
        edit_count=1,
        is_sealed=False,
        created_by_id="u1",
        change_summary=None,
        parent_version_id=None,
        is_current=True,
    )
    version_b = ContentVersion(
        lesson_id=1,
        content_type=ContentType.SUMMARY.value,
        content="# Title\n\nParagraph one.\n\nParagraph two.",
        version_number=2,
        version_source=VersionSource.HUMAN.value,
        created_at=datetime.utcnow(),
        last_edited_at=None,
        edit_count=1,
        is_sealed=False,
        created_by_id="u1",
        change_summary=None,
        parent_version_id=None,
        is_current=True,
    )

    diff = compute_diff(version_a, version_b)

    assert diff["type"] == "text"
    assert diff["diff"] == ""
