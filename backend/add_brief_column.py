"""Migration script to add brief column to lesson table"""
import sqlite3
from pathlib import Path

# Database path
db_path = Path(__file__).parent / "data" / "lessons.db"

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Add brief column
    cursor.execute("ALTER TABLE lesson ADD COLUMN brief TEXT")
    conn.commit()
    print("SUCCESS: Added 'brief' column to lesson table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("INFO: Column 'brief' already exists")
    else:
        print(f"ERROR: {e}")
finally:
    conn.close()

