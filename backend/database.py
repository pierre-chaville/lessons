from sqlmodel import SQLModel, create_engine, Session
from pathlib import Path

# Create database directory if it doesn't exist
db_path = Path(__file__).parent / "data"
db_path.mkdir(exist_ok=True)

# SQLite database URL
DATABASE_URL = f"sqlite:///{db_path}/lessons.db"

# Create engine
engine = create_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})


def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session"""
    with Session(engine) as session:
        yield session

