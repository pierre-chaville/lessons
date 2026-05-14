"""Utilities for summary <-> edited alignment metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.dp_align_core import align_dp_texts
from services.edited_transcript import compute_markdown_hash, markdown_to_paragraphs

MIN_SUMMARY_ALIGNMENT_SCORE = 0.2


def _paragraphs(text: str) -> list[str]:
    rows = markdown_to_paragraphs(text)
    if not rows and text.strip():
        rows = [text.strip()]
    return rows


def _split_blocks(markdown: str) -> list[str]:
    text = str(markdown or "").strip()
    if not text:
        return []
    return [block.strip() for block in text.split("\n\n") if block.strip()]


def _is_non_alignable_summary_block(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    return False


def build_summary_alignment_metadata(
    summary_markdown: str,
    edited_markdown: str,
    min_alignment_score: float = MIN_SUMMARY_ALIGNMENT_SCORE,
) -> dict[str, Any]:
    summary_blocks = _split_blocks(summary_markdown)
    summary_paragraphs = _paragraphs(summary_markdown)
    edited_paragraphs = _paragraphs(edited_markdown)

    alignment = [
        {"match_score": 0.0, "start_index": None, "end_index": None}
        for _ in summary_blocks
    ]
    alignable_indices: list[int] = []
    alignable_texts: list[str] = []
    for idx, block in enumerate(summary_blocks):
        if _is_non_alignable_summary_block(block):
            continue
        alignable_indices.append(idx)
        alignable_texts.append(block)

    if alignable_texts and edited_paragraphs:
        aligned = align_dp_texts(transcript=edited_paragraphs, edited=alignable_texts)
        for local_idx, row in enumerate(aligned):
            global_idx = alignable_indices[local_idx]
            score = float(row.get("match_score", 0.0))
            start_index = row.get("source_start_index")
            end_index = row.get("source_end_index")
            is_candidate = (
                isinstance(start_index, int)
                and isinstance(end_index, int)
                and 0 <= start_index <= end_index < len(edited_paragraphs)
            )
            should_align = is_candidate and score >= min_alignment_score
            alignment[global_idx] = {
                "match_score": score,
                "start_index": start_index if should_align else None,
                "end_index": end_index if should_align else None,
            }

    return {
        "summary_alignment": alignment,
        "summary_hash": compute_markdown_hash(summary_markdown) if summary_markdown else None,
        "edited_markdown_hash": compute_markdown_hash(edited_markdown) if edited_markdown else None,
        "summary_aligned_at": datetime.utcnow().isoformat(),
        "summary_paragraph_count": len(summary_paragraphs),
        "edited_paragraph_count": len(edited_paragraphs),
    }

