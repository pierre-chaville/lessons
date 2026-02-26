"""Hashid encoding / decoding utilities for entity IDs (lessons, courses, themes)."""

import os
from pathlib import Path
from hashids import Hashids
from fastapi import HTTPException
from dotenv import load_dotenv, find_dotenv

# Lazy singleton
_hashids: Hashids | None = None


def _load_env() -> None:
    """Load .env files so HASHIDS_SALT is available."""
    load_dotenv(find_dotenv(usecwd=True), override=True, encoding="utf-8-sig")
    load_dotenv(Path(__file__).parent / ".env", override=True, encoding="utf-8-sig")
    load_dotenv(Path(__file__).parent.parent / ".env", override=True, encoding="utf-8-sig")


def _get_hashids() -> Hashids:
    global _hashids
    if _hashids is None:
        _load_env()
        salt = os.getenv("HASHIDS_SALT", "lessons-default-salt")
        _hashids = Hashids(salt=salt, min_length=8)
    return _hashids


def encode_id(int_id: int) -> str:
    """Encode a numeric ID into a hashid string."""
    return _get_hashids().encode(int_id)


def decode_id(hashid: str) -> int:
    """Decode a hashid string back to a numeric ID.

    Raises HTTPException(404) if the hashid is invalid.
    """
    result = _get_hashids().decode(hashid)
    if not result:
        raise HTTPException(status_code=404, detail="Invalid identifier")
    return result[0]
