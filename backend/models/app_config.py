"""SQLModel table model for application configuration."""

from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON
from typing import Optional, Dict, Any


class AppConfig(SQLModel, table=True):
    """Application configuration stored as a single JSON record."""

    __tablename__ = "app_config"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
