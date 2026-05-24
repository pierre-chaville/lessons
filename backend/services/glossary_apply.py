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


@dataclass(frozen=True)
class GlossaryReplacement:
    standard: str
    variation: str
    exact_case: bool
    count: int


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
    normalized, _ = apply_glossary_to_text_with_report(text, rules)
    return normalized


def apply_glossary_to_text_with_report(
    text: str,
    rules: list[GlossaryRule],
) -> tuple[str, list[dict[str, Any]]]:
    """Apply glossary replacements and return replacement stats."""
    normalized = str(text or "")
    if not normalized or not rules:
        return normalized, []

    replacements: list[GlossaryReplacement] = []
    for rule in rules:
        for variation in rule.variations:
            pattern = re.compile(
                rf"(?<!\w){re.escape(variation)}(?!\w)",
                0 if rule.exact_case else re.IGNORECASE,
            )
            normalized, count = pattern.subn(rule.standard, normalized)
            if count > 0:
                replacements.append(
                    GlossaryReplacement(
                        standard=rule.standard,
                        variation=variation,
                        exact_case=rule.exact_case,
                        count=count,
                    )
                )
    return normalized, [
        {
            "standard": item.standard,
            "variation": item.variation,
            "exact_case": item.exact_case,
            "count": item.count,
        }
        for item in replacements
    ]


def apply_glossary_to_segments(
    segments: list[dict[str, Any]] | list[Any],
    rules: list[GlossaryRule],
) -> list[dict[str, Any]]:
    """Apply glossary replacements to transcript-like segment lists."""
    normalized, _ = apply_glossary_to_segments_with_report(segments, rules)
    return normalized


def apply_glossary_to_segments_with_report(
    segments: list[dict[str, Any]] | list[Any],
    rules: list[GlossaryRule],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply glossary replacements to transcript-like segment lists with stats."""
    if not segments:
        return [], []
    normalized: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for seg in segments:
        if isinstance(seg, dict):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
            text = str(seg.get("text", ""))
        else:
            start = float(getattr(seg, "start", 0.0))
            end = float(getattr(seg, "end", 0.0))
            text = str(getattr(seg, "text", ""))
        replaced_text, segment_report = apply_glossary_to_text_with_report(text, rules)
        report.extend(segment_report)
        normalized.append(
            {
                "start": start,
                "end": end,
                "text": replaced_text,
            }
        )
    return normalized, merge_glossary_reports(report)


def merge_glossary_reports(report: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge repeated replacement entries into aggregated counts."""
    counts: dict[tuple[str, str, bool], int] = {}
    for item in report:
        standard = str(item.get("standard", ""))
        variation = str(item.get("variation", ""))
        exact_case = bool(item.get("exact_case", False))
        count = int(item.get("count", 0) or 0)
        if not standard or not variation or count <= 0:
            continue
        key = (standard, variation, exact_case)
        counts[key] = counts.get(key, 0) + count
    merged = [
        {
            "standard": standard,
            "variation": variation,
            "exact_case": exact_case,
            "count": count,
        }
        for (standard, variation, exact_case), count in counts.items()
    ]
    merged.sort(key=lambda item: (-item["count"], item["standard"], item["variation"]))
    return merged
