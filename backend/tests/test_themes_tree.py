"""Unit tests for hierarchical themes."""

from __future__ import annotations

from datetime import datetime
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlmodel import Session, SQLModel, create_engine, select

import crud
from models.lesson import Lesson
from models.theme import Theme
from routers.themes import _build_tree, _get_lesson_counts


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _lesson(session: Session, theme_ids: list[int], **kwargs) -> Lesson:
    lesson = Lesson(
        title=kwargs.pop("title", "Lesson"),
        filename=kwargs.pop("filename", "file.mp3"),
        date=kwargs.pop("date", datetime.utcnow()),
        transcript=[],
        status="draft",
        **kwargs,
    )
    lesson.set_themes(theme_ids)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def test_theme_tree_counts_include_children_and_skip_deleted_lessons() -> None:
    with _session() as session:
        root = crud.create_theme(session, "Root")
        child = crud.create_theme(session, "Child", parent_id=root.id)
        _lesson(session, [root.id])
        _lesson(session, [root.id], deleted_at=datetime.utcnow(), deleted_by="admin")
        _lesson(session, [child.id])
        _lesson(session, [child.id], deleted_at=datetime.utcnow(), deleted_by="admin")

        themes = list(session.exec(select(Theme)).all())
        lesson_counts = _get_lesson_counts(session)
        tree = _build_tree(themes, lesson_counts)

        assert lesson_counts == {root.id: 1, child.id: 1}
        assert tree[0].id == root.id
        assert tree[0].lesson_count == 2
        assert tree[0].children[0].id == child.id
        assert tree[0].children[0].lesson_count == 1


def test_create_theme_appends_sort_order_among_siblings() -> None:
    with _session() as session:
        first = crud.create_theme(session, "First")
        second = crud.create_theme(session, "Second")
        child = crud.create_theme(session, "Child", parent_id=first.id)

        assert first.sort_order == 0
        assert second.sort_order == 1
        assert child.sort_order == 0
        assert child.parent_id == first.id


def test_delete_theme_reparents_children() -> None:
    with _session() as session:
        root = crud.create_theme(session, "Root")
        child = crud.create_theme(session, "Child", parent_id=root.id)
        grandchild = crud.create_theme(session, "Grandchild", parent_id=child.id)

        lesson = _lesson(session, [child.id, root.id])

        assert crud.delete_theme(session, child.id) is True

        session.refresh(grandchild)
        session.refresh(lesson)
        assert grandchild.parent_id == root.id
        assert crud.get_theme(session, child.id) is None
        assert lesson.get_themes() == [root.id]
