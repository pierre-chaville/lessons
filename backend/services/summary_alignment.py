"""Utilities for summary <-> edited alignment metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.dp_align_core import align_dp_texts
from services.edited_transcript import compute_markdown_hash, markdown_to_paragraphs


def _paragraphs(text: str) -> list[str]:
    rows = markdown_to_paragraphs(text)
    if not rows and text.strip():
        rows = [text.strip()]
    return rows


def build_summary_alignment_metadata(
    summary_markdown: str, edited_markdown: str
) -> dict[str, Any]:
    summary_paragraphs = _paragraphs(summary_markdown)
    edited_paragraphs = _paragraphs(edited_markdown)

    alignment = []
    if summary_paragraphs and edited_paragraphs:
        aligned = align_dp_texts(transcript=edited_paragraphs, edited=summary_paragraphs)
        for row in aligned:
            alignment.append(
                {
                    "match_score": float(row.get("match_score", 0.0)),
                    "start_index": row.get("source_start_index"),
                    "end_index": row.get("source_end_index"),
                }
            )

    return {
        "summary_alignment": alignment,
        "summary_hash": compute_markdown_hash(summary_markdown) if summary_markdown else None,
        "edited_markdown_hash": compute_markdown_hash(edited_markdown) if edited_markdown else None,
        "summary_aligned_at": datetime.utcnow().isoformat(),
        "summary_paragraph_count": len(summary_paragraphs),
        "edited_paragraph_count": len(edited_paragraphs),
    }

