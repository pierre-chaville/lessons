import os

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATBASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (or DATBASE_URL). Check your .env.")

# Create engine
engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session"""
    with Session(engine) as session:
        yield session

