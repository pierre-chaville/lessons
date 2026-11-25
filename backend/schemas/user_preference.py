"""Pydantic schemas for the signed-in user's own preferences (/me/preferences)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HebrewPrimaryForm = Literal["translit", "vocalized", "unvocalized"]
HebrewSupplementForm = Literal["none", "alternate", "translation"]
HebrewSupplementFrequency = Literal["first", "every"]


class HebrewDisplaySettings(BaseModel):
    """How Hebrew terms are displayed in lessons (mirrors frontend useHebrewDisplay)."""

    model_config = ConfigDict(extra="forbid")

    primary: HebrewPrimaryForm = Field(description="Form shown in the body of the text")
    supplement: HebrewSupplementForm = Field(
        description="Form added in parentheses; 'alternate' = Hebrew if primary is the "
        "transliteration, transliteration otherwise"
    )
    frequency: HebrewSupplementFrequency = Field(
        description="Supplementary form on the first occurrence only, or on every occurrence"
    )
    quotations_in_hebrew: bool = Field(
        description="Biblical verses and Talmud quotations always shown in Hebrew"
    )


class UserPreferencesResponse(BaseModel):
    """Preferences of the signed-in user; ``None`` = never saved (use the defaults)."""

    hebrew_display: HebrewDisplaySettings | None = None
