from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import func

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parents[0]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.app_config import AppConfig  # noqa: E402
from models.course import Course  # noqa: E402
from models.lesson import Lesson  # noqa: E402
from models.task import Task  # noqa: E402
from models.theme import Theme  # noqa: E402


def _get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATBASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set (or DATBASE_URL). Check your .env."
        )
    return db_url


def _get_sqlite_url() -> str:
    db_path = Path(__file__).resolve().parents[1] / "data" / "lessons.db"
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

    print(f"Migrating from {sqlite_url} to {postgres_url}")
    sqlite_engine = create_engine(
        sqlite_url, connect_args={"check_same_thread": False}
    )
    postgres_engine = create_engine(postgres_url)

    print("Creating tables in Postgres...")
    SQLModel.metadata.create_all(postgres_engine)

    print("Ensuring target tables are empty...")
    table_order = [Course, Theme, Lesson, Task, AppConfig]

    with Session(postgres_engine) as target_session:
        for model in table_order:
            _ensure_target_empty(target_session, model)

    print("Copying data from SQLite to Postgres...")
    with Session(sqlite_engine) as source_session, Session(
        postgres_engine
    ) as target_session:
        for model in table_order:
            copied = _copy_table(source_session, target_session, model)
            print(f"{model.__tablename__}: copied {copied} rows")

    print("Migration completed.")


if __name__ == "__main__":
    main()
