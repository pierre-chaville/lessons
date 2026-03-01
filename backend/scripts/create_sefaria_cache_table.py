"""Migration script to create sefaria_cache table"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from database import DATABASE_URL
from models import SefariaCache
from sqlmodel import SQLModel

engine = create_engine(DATABASE_URL)


def create_sefaria_cache_table():
    """Create the sefaria_cache table"""
    print("Creating sefaria_cache table...")
    # This will only create tables that don't exist yet
    SQLModel.metadata.create_all(engine, tables=[SefariaCache.__table__])
    print("Successfully created sefaria_cache table")

print("Creating sefaria_cache table...")
# This will only create tables that don't exist yet
SQLModel.metadata.create_all(engine, tables=[SefariaCache.__table__])
print("Successfully created sefaria_cache table")

if __name__ == "__main__":
    create_sefaria_cache_table()
