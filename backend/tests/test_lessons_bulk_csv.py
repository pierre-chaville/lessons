"""Tests for admin bulk CSV lesson import/export helpers."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

import crud
from models.lesson import Lesson
from services.lessons import export_lessons_csv, import_lessons_csv


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_export_lessons_csv_contains_identification_columns() -> None:
    with _session() as session:
        lesson = Lesson(
            title="CSV Lesson",
            filename="file.mp3",
            date=datetime(2026, 1, 10, 0, 0, 0),
            status="draft",
        )
        session.add(lesson)
        session.commit()

        csv_payload = export_lessons_csv(session)

        assert "id,title,filename,status,date,course_id,course_name,theme_ids,theme_names,editor_ids" in csv_payload
        assert "CSV Lesson" in csv_payload


def test_import_lessons_csv_updates_only_changed_fields() -> None:
    with _session() as session:
        course_a = crud.create_course(session, "Course A")
        course_b = crud.create_course(session, "Course B")
        theme_a = crud.create_theme(session, "Theme A")
        theme_b = crud.create_theme(session, "Theme B")

        lesson = Lesson(
            title="Bulk Edit Lesson",
            filename="file.mp3",
            date=datetime(2026, 1, 10, 0, 0, 0),
            status="draft",
            course_id=course_a.id,
        )
        lesson.set_themes([theme_a.id])
        session.add(lesson)
        session.commit()
        session.refresh(lesson)
        crud.set_lesson_editors(session, lesson.id, ["editor_a"], assigned_by="seed")
        session.commit()

        csv_payload = (
            "id,title,filename,status,date,course_id,course_name,theme_ids,theme_names,editor_ids\n"
            f"{lesson.id},Bulk Edit Lesson,file.mp3,validated,2026-02-15,{course_b.id},Course B,{theme_b.id},Theme B,editor_b\n"
        )
        result = import_lessons_csv(
            session=session,
            csv_bytes=csv_payload.encode("utf-8"),
            assigned_by="admin_user",
        )

        updated = crud.get_lesson(session, lesson.id)
        assert updated is not None
        assert updated.status == "validated"
        assert updated.date.date().isoformat() == "2026-02-15"
        assert updated.course_id == course_b.id
        assert updated.get_themes() == [theme_b.id]
        assert [e.user_id for e in crud.get_lesson_editors(session, lesson.id)] == ["editor_b"]

        assert result["updated_count"] == 1
        assert result["error_count"] == 0
        assert result["updated_ids"] == [lesson.id]
