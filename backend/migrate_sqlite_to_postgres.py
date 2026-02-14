from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import func

from models import AppConfig, Course, Lesson, Task, Theme


def _get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATBASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set (or DATBASE_URL). Check your .env."
        )
    return db_url


def _get_sqlite_url() -> str:
    db_path = Path(__file__).parent / "data" / "lessons.db"
    return f"sqlite:///{db_path}"


def _ensure_target_empty(session: Session, model) -> None:
    count = session.exec(select(func.count()).select_from(model)).one()
    if count:
        raise RuntimeError(
            f"Target table '{model.__tablename__}' is not empty ({count} rows)."
        )


def _copy_table(source_session: Session, target_session: Session, model) -> int:
    rows = source_session.exec(select(model)).all()
    if not rows:
        return 0

    column_names = [column.name for column in model.__table__.columns]
    for row in rows:
        data = {name: getattr(row, name) for name in column_names}
        target_session.add(model(**data))
    target_session.commit()
    return len(rows)


def main() -> None:
    load_dotenv(override=True)

    sqlite_url = _get_sqlite_url()
    postgres_url = _get_database_url()

    sqlite_engine = create_engine(
        sqlite_url, connect_args={"check_same_thread": False}
    )
    postgres_engine = create_engine(postgres_url)

    SQLModel.metadata.create_all(postgres_engine)

    table_order = [Course, Theme, Lesson, Task, AppConfig]

    with Session(postgres_engine) as target_session:
        for model in table_order:
            _ensure_target_empty(target_session, model)

    with Session(sqlite_engine) as source_session, Session(
        postgres_engine
    ) as target_session:
        for model in table_order:
            copied = _copy_table(source_session, target_session, model)
            print(f"{model.__tablename__}: copied {copied} rows")

    print("Migration completed.")


if __name__ == "__main__":
    main()
