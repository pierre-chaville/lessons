"""Glossary application helpers for transcript/markdown normalization."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlmodel import Session

import crud


@dataclass(frozen=True)
class GlossaryRule:
    standard: str
    variations: tuple[str, ...]
    exact_case: bool


def load_glossary_rules(session: Session) -> list[GlossaryRule]:
    """Load glossary entries as normalized replacement rules."""
    entries = crud.get_all_glossary_entries(session)
    rules: list[GlossaryRule] = []
    for entry in entries:
        standard = str(entry.standard or "").strip()
        if not standard:
            continue
        variations = [str(v).strip() for v in (entry.variations or []) if str(v).strip()]
        if standard not in variations:
            variations.append(standard)
        # Longest first helps avoid partial replacements (e.g. "Ohr Ein" before "Ohr").
        variations = sorted(set(variations), key=len, reverse=True)
        rules.append(
            GlossaryRule(
                standard=standard,
                variations=tuple(variations),
                exact_case=bool(entry.exact_case),
            )
        )
    return rules


def apply_glossary_to_text(text: str, rules: list[GlossaryRule]) -> str:
    """Apply glossary replacements to free text."""
    normalized = str(text or "")
    if not normalized or not rules:
        return normalized

    for rule in rules:
        for variation in rule.variations:
            pattern = re.compile(
                rf"(?<!\w){re.escape(variation)}(?!\w)",
                0 if rule.exact_case else re.IGNORECASE,
            )
            normalized = pattern.sub(rule.standard, normalized)
    return normalized


def apply_glossary_to_segments(
    segments: list[dict[str, Any]] | list[Any],
    rules: list[GlossaryRule],
) -> list[dict[str, Any]]:
    """Apply glossary replacements to transcript-like segment lists."""
    if not segments:
        return []
    normalized: list[dict[str, Any]] = []
    for seg in segments:
        if isinstance(seg, dict):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
            text = str(seg.get("text", ""))
        else:
            start = float(getattr(seg, "start", 0.0))
            end = float(getattr(seg, "end", 0.0))
            text = str(getattr(seg, "text", ""))
        normalized.append(
            {
                "start": start,
                "end": end,
                "text": apply_glossary_to_text(text, rules),
            }
        )
    return normalized
