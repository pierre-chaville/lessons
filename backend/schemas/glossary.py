"""Pydantic schemas for glossary API."""

from typing import List

from pydantic import BaseModel, Field, field_validator


class GlossaryEntryBase(BaseModel):
    standard: str = Field(min_length=1)
    variations: List[str] = Field(default_factory=list)
    exact_case: bool = False

    @field_validator("standard")
    @classmethod
    def _validate_standard(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("standard cannot be empty")
        return trimmed

    @field_validator("variations")
    @classmethod
    def _validate_variations(cls, values: List[str]) -> List[str]:
        cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        seen = set()
        unique: List[str] = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique


class GlossaryEntryCreate(GlossaryEntryBase):
    pass


class GlossaryEntryUpdate(BaseModel):
    standard: str | None = None
    variations: List[str] | None = None
    exact_case: bool | None = None

    @field_validator("standard")
    @classmethod
    def _validate_standard(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("standard cannot be empty")
        return trimmed

    @field_validator("variations")
    @classmethod
    def _validate_variations(cls, values: List[str] | None) -> List[str] | None:
        if values is None:
            return None
        cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        seen = set()
        unique: List[str] = []
        for item in cleaned:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique


class GlossaryEntryResponse(BaseModel):
    id: int
    hashid: str = ""
    standard: str
    variations: List[str]
    exact_case: bool

    class Config:
        from_attributes = True
