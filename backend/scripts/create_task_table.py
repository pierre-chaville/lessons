"""Migration script to create task table"""
from sqlalchemy import create_engine
from database import DATABASE_URL
from models import Task
from sqlmodel import SQLModel

engine = create_engine(DATABASE_URL)

def create_task_table():
    """Create the task table"""
    print("Creating task table...")
    # This will only create tables that don't exist yet
    SQLModel.metadata.create_all(engine, tables=[Task.__table__])
    print("Successfully created task table")

if __name__ == "__main__":
    create_task_table()

