import os
import logging

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text, inspect

load_dotenv(override=True)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATBASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (or DATBASE_URL). Check your .env.")

# Create engine
engine = create_engine(DATABASE_URL, echo=False)


def _run_migrations():
    """Add missing columns to existing tables (lightweight auto-migration)."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "lesson" in tables:
        columns = {col["name"] for col in inspector.get_columns("lesson")}
        if "status" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE lesson ADD COLUMN status VARCHAR NOT NULL DEFAULT 'draft'"
                ))
            logger.info("Migration: added 'status' column to lesson table")

    if "course" in tables:
        columns = {col["name"] for col in inspector.get_columns("course")}
        if "parent_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE course ADD COLUMN parent_id INTEGER REFERENCES course(id)"
                ))
            logger.info("Migration: added 'parent_id' column to course table")


def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def get_session():
    """Get database session"""
    with Session(engine) as session:
        yield session

