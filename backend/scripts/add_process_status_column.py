"""Migration script to add process_status column to lesson table.

Values: transcript, edition, sources_extraction, sources_checking, summary, or NULL (not processing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from database import DATABASE_URL

engine = create_engine(DATABASE_URL)


def add_process_status_column():
    """Add process_status column to lesson table"""
    with engine.connect() as conn:
        try:
            conn.execute(
                text("ALTER TABLE lesson ADD COLUMN process_status VARCHAR")
            )
            conn.commit()
            print("SUCCESS: Added 'process_status' column to lesson table")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("INFO: Column 'process_status' already exists")
            else:
                print(f"ERROR: {e}")


if __name__ == "__main__":
    add_process_status_column()
