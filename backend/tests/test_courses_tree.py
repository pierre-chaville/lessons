"""Unit tests for course tree lesson counts."""

from __future__ import annotations

from datetime import datetime
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlmodel import Session, SQLModel, create_engine

from models.course import Course
from models.lesson import Lesson
from routers.courses import _build_tree, _get_lesson_counts


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _course(session: Session, name: str, parent_id: int | None = None) -> Course:
    course = Course(name=name, parent_id=parent_id)
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


def _lesson(session: Session, course_id: int, **kwargs) -> Lesson:
    values = {
        "title": "Lesson",
        "filename": "file.mp3",
        "course_id": course_id,
        "date": datetime.utcnow(),
        "transcript": [],
        "status": "draft",
    }
    values.update(kwargs)
    lesson = Lesson(**values)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def test_course_tree_counts_only_active_lessons() -> None:
    with _session() as session:
        root = _course(session, "Root")
        child = _course(session, "Child", parent_id=root.id)
        _lesson(session, root.id)
        _lesson(session, root.id, deleted_at=datetime.utcnow(), deleted_by="admin")
        _lesson(session, child.id)
        _lesson(session, child.id, deleted_at=datetime.utcnow(), deleted_by="admin")

        lesson_counts = _get_lesson_counts(session)
        tree = _build_tree([root, child], lesson_counts)

        assert lesson_counts == {root.id: 1, child.id: 1}
        assert tree[0].lesson_count == 2
        assert tree[0].children[0].lesson_count == 1
