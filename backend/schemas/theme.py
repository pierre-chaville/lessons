"""Pydantic schemas for theme API requests and responses."""

from pydantic import BaseModel


class ThemeCreate(BaseModel):
    name: str


class ThemeUpdate(BaseModel):
    name: str


class ThemeResponse(BaseModel):
    """Theme response with hashid."""

    id: int
    hashid: str = ""
    name: str

    class Config:
        from_attributes = True
