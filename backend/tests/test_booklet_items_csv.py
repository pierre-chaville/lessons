from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

import crud
from models.booklet import Booklet, BookletItem, BookletItemType
from models.lesson import Lesson
from services.booklet import export_booklet_items_csv, get_booklet_items, import_booklet_items_csv


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_export_booklet_items_csv_includes_session_id_course_path_and_date() -> None:
    with _session() as session:
        parent_course = crud.create_course(session, "Ragim")
        child_course = crud.create_course(session, "Shavouoth", parent_id=parent_course.id)
        booklet = Booklet(title="CSV Booklet")
        lesson = Lesson(
            title="Lesson A",
            filename="lesson-a.mp3",
            date=datetime(2026, 5, 1, 0, 0, 0),
            course_id=child_course.id,
            status="validated",
        )
        session.add(booklet)
        session.add(lesson)
        session.commit()
        session.refresh(booklet)
        session.refresh(lesson)

        session.add(
            BookletItem(
                booklet_id=booklet.id,
                position=1,
                item_type=BookletItemType.LESSON,
                lesson_id=lesson.id,
            )
        )
        session.commit()

        csv_payload = export_booklet_items_csv(session, booklet.id)

        assert "position,item_type,session_id,title,course_path,date,status" in csv_payload
        assert f"1,lesson,{lesson.id},Lesson A,Ragim / Shavouoth,2026-05-01,validated" in csv_payload


def test_import_booklet_items_csv_replaces_booklet_items(monkeypatch) -> None:
    with _session() as session:
        monkeypatch.setattr("services.booklet.log_event", lambda *args, **kwargs: None)
        booklet = Booklet(title="Import Booklet")
        lesson_1 = Lesson(title="Lesson 1", filename="l1.mp3", date=datetime(2026, 5, 1, 0, 0, 0))
        lesson_2 = Lesson(title="Lesson 2", filename="l2.mp3", date=datetime(2026, 5, 2, 0, 0, 0))
        session.add(booklet)
        session.add(lesson_1)
        session.add(lesson_2)
        session.commit()
        session.refresh(booklet)
        session.refresh(lesson_1)
        session.refresh(lesson_2)

        # Seed one existing row to verify import fully replaces composition.
        session.add(
            BookletItem(
                booklet_id=booklet.id,
                position=1,
                item_type=BookletItemType.LESSON,
                lesson_id=lesson_1.id,
            )
        )
        session.commit()

        csv_payload = (
            "position,item_type,session_id,title,course_path,date,status\n"
            f"1,lesson,{lesson_2.id},Custom session title,,,\n"
            "2,chapter,,Chapter separator,,,\n"
        )
        result = import_booklet_items_csv(
            session=session,
            booklet_id=booklet.id,
            csv_bytes=csv_payload.encode("utf-8"),
            actor={"sub": "admin_user", "role": "admin"},
        )

        rows = get_booklet_items(session, booklet.id)
        assert [row.position for row in rows] == [1, 2]
        assert [row.item_type for row in rows] == [BookletItemType.LESSON, BookletItemType.CHAPTER]
        assert rows[0].lesson_id == lesson_2.id
        assert rows[0].custom_title == "Custom session title"
        assert rows[1].chapter_title == "Chapter separator"

        assert result == {
            "imported_count": 2,
            "lesson_count": 1,
            "chapter_count": 1,
            "errors": [],
        }
