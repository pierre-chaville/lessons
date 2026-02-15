"""Pydantic schemas for theme API requests."""

from pydantic import BaseModel


class ThemeCreate(BaseModel):
    name: str


class ThemeUpdate(BaseModel):
    name: str
