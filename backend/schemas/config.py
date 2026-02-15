"""Pydantic schemas for configuration API requests."""

from pydantic import BaseModel
from typing import Dict, Any


class ConfigUpdate(BaseModel):
    config: Dict[str, Any]
