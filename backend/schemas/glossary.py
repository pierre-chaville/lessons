"""Pydantic schemas for the Hebrew-keyed glossary API."""

from datetime import datetime
from enum import Enum
from typing import Any, List

from pydantic import BaseModel, Field, field_validator

from hebrew_text import contains_hebrew_letter


class GlossaryType(str, Enum):
    TERM = "term"
    EXPRESSION = "expression"
    QUOTATION = "quotation"
    PROPER_NAME = "proper_name"
    BOOK = "book"
    AUTHOR = "author"
    HOLIDAY = "holiday"
    PLACE = "place"


class GlossaryCaseFlag(str, Enum):
    """Capitalization rule applied when the transliteration is displayed."""

    LOWER = "lower"
    CAPITALIZE = "capitalize"
    KEEP = "keep"


class GlossaryStatus(str, Enum):
    VALIDATED = "validated"
    AUTO = "auto"
    REJECTED = "rejected"


class GlossarySource(str, Enum):
    MIGRATION = "migration"
    LLM = "llm"
    MANUAL = "manual"


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _clean_aliases(values: List[str]) -> List[str]:
    unique: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if item and item not in unique:
            unique.append(item)
    return unique


def _validate_hebrew(value: str) -> str:
    trimmed = value.strip()
    if not contains_hebrew_letter(trimmed):
        raise ValueError("hebrew must contain Hebrew letters")
    return trimmed


_OPTIONAL_TEXT_FIELDS = (
    "translit",
    "context_lesson",
    "context_paragraph",
    "translation",
    "sefaria_title",
    "sefaria_ref",
)


class GlossaryEntryCreate(BaseModel):
    """Create payload. hebrew_norm / hebrew_cons are computed server-side."""

    hebrew: str = Field(min_length=1)
    translit: str | None = None
    aliases: List[str] = Field(default_factory=list)
    type: GlossaryType = GlossaryType.TERM
    case_flag: GlossaryCaseFlag = GlossaryCaseFlag.LOWER
    status: GlossaryStatus = GlossaryStatus.VALIDATED
    source: GlossarySource = GlossarySource.MANUAL
    context_lesson: str | None = None
    context_paragraph: str | None = None
    translation: str | None = None
    sefaria_title: str | None = None
    sefaria_ref: str | None = None

    @field_validator("hebrew")
    @classmethod
    def _validate_hebrew(cls, value: str) -> str:
        return _validate_hebrew(value)

    @field_validator("aliases")
    @classmethod
    def _validate_aliases(cls, values: List[str]) -> List[str]:
        return _clean_aliases(values)

    @field_validator(*_OPTIONAL_TEXT_FIELDS)
    @classmethod
    def _validate_texts(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class GlossaryEntryUpdate(BaseModel):
    """Partial update. Fields left out are unchanged; null clears optional text."""

    hebrew: str | None = None
    translit: str | None = None
    aliases: List[str] | None = None
    type: GlossaryType | None = None
    case_flag: GlossaryCaseFlag | None = None
    status: GlossaryStatus | None = None
    source: GlossarySource | None = None
    context_lesson: str | None = None
    context_paragraph: str | None = None
    translation: str | None = None
    sefaria_title: str | None = None
    sefaria_ref: str | None = None

    @field_validator("hebrew")
    @classmethod
    def _validate_hebrew(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("hebrew cannot be null")
        return _validate_hebrew(value)

    @field_validator("aliases")
    @classmethod
    def _validate_aliases(cls, values: List[str] | None) -> List[str] | None:
        return None if values is None else _clean_aliases(values)

    @field_validator(*_OPTIONAL_TEXT_FIELDS)
    @classmethod
    def _validate_texts(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class GlossaryEntryResponse(BaseModel):
    id: int
    hashid: str = ""
    hebrew: str
    hebrew_norm: str
    hebrew_cons: str
    translit: str | None
    aliases: List[str]
    type: GlossaryType
    case_flag: GlossaryCaseFlag
    status: GlossaryStatus
    source: GlossarySource
    context_lesson: str | None
    context_paragraph: str | None
    translation: str | None
    sefaria_title: str | None
    sefaria_ref: str | None
    created_at: datetime
    updated_at: datetime


class GlossaryEntryListResponse(BaseModel):
    items: List[GlossaryEntryResponse]
    total: int
    page: int
    per_page: int


class GlossaryImportResult(BaseModel):
    created: int
    updated: int
    total: int


class GlossaryCompletion(BaseModel):
    """LLM completion of one glossary entry (structured output)."""

    id: int = Field(description="Id of the entry, exactly as given in the input.")
    translit: str = Field(description="Transliteration used in the lessons.")
    aliases: List[str] = Field(description="Other common transliterations (may be empty).")
    type: GlossaryType = Field(description="Kind of entry.")
    case_flag: GlossaryCaseFlag = Field(
        description="lower: common noun; capitalize: proper name, book, holiday...; keep: keep as written."
    )
    translation: str | None = Field(description="Short translation or explanation.")
    sefaria_title: str | None = Field(
        description="Sefaria title for books, authors and quotations; null otherwise or when unsure."
    )
    sefaria_ref: str | None = Field(
        description="Sefaria reference for quotations; null otherwise or when unsure."
    )


class GlossaryCompletionBatch(BaseModel):
    """LLM completions for a batch of glossary entries (structured output)."""

    entries: List[GlossaryCompletion] = Field(description="One result per input entry.")


class GlossaryCompletionLaunch(BaseModel):
    """Result of a request to complete pending glossary entries."""

    task_id: int | None
    pending_entries: int


class GlossaryCompletionStatus(BaseModel):
    """Entries awaiting completion and the latest glossary completion task."""

    pending_entries: int
    task_id: int | None = Field(default=None, description="Latest glossary task, if any")
    task_status: str | None = Field(default=None, description="pending, running, completed, failed…")
    task_error: str | None = None
    task_result: dict[str, Any] | None = None
