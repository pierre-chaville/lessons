"""Utilities for edited transcript payloads (markdown + alignment)."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any

from services.dp_align_core import align_dp_texts
from schemas.lesson import EditedAlignment, EditedTranscript, Segment


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_markdown_hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def compute_transcript_hash(transcript: list[dict[str, Any]] | list[Segment]) -> str:
    serialized = []
    for seg in transcript:
        if isinstance(seg, dict):
            serialized.append(
                {
                    "start": float(seg.get("start", 0.0)),
                    "end": float(seg.get("end", 0.0)),
                    "text": str(seg.get("text", "")),
                }
            )
        else:
            serialized.append(
                {"start": float(seg.start), "end": float(seg.end), "text": str(seg.text)}
            )
    return hashlib.sha256(_canonical_json(serialized).encode("utf-8")).hexdigest()


def markdown_to_paragraphs(markdown: str) -> list[str]:
    """Split markdown into paragraph-like blocks for alignment/source extraction."""
    raw = str(markdown or "").strip()
    if not raw:
        return []

    blocks = re.split(r"\n\s*\n+", raw)
    paragraphs: list[str] = []
    for block in blocks:
        lines = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = re.sub(r"^\s{0,3}(#{1,6}\s+|[-*+]\s+|\d+\.\s+|>\s?)", "", stripped)
            lines.append(stripped)
        text = " ".join(lines).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def normalize_edited_transcript_payload(value: Any) -> dict[str, Any]:
    """Normalize edited transcript payload to the canonical object shape.

    Supports:
    - canonical dict payload
    - legacy list[{"start","end","text","sources"}]
    - JSON string containing one of the above
    """
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    if isinstance(value, str):
        value = json.loads(value)

    if isinstance(value, list):
        markdown = "\n\n".join(str(item.get("text", "")).strip() for item in value if isinstance(item, dict)).strip()
        sources = [item.get("sources", []) if isinstance(item, dict) else [] for item in value]
        alignment_rows = []
        for item in value:
            if not isinstance(item, dict):
                continue
            alignment_rows.append(
                EditedAlignment(
                    start=item.get("start"),
                    end=item.get("end"),
                    match_score=float(item.get("match_score", 1.0)),
                    start_index=item.get("start_index", item.get("source_start_index")),
                    end_index=item.get("end_index", item.get("source_end_index")),
                )
            )
        payload = EditedTranscript(
            markdown=markdown,
            sources=sources,
            alignment=alignment_rows,
            markdown_hash=compute_markdown_hash(markdown) if markdown else None,
            aligned_at=datetime.utcnow() if alignment_rows else None,
        )
        return payload.model_dump(mode="json")

    if isinstance(value, dict):
        markdown = str(value.get("markdown", ""))
        normalized_alignment = []
        for row in value.get("alignment", []) or []:
            if not isinstance(row, dict):
                continue
            normalized_alignment.append(
                EditedAlignment(
                    start=row.get("start"),
                    end=row.get("end"),
                    match_score=float(row.get("match_score", 0.0)),
                    start_index=row.get("start_index", row.get("source_start_index")),
                    end_index=row.get("end_index", row.get("source_end_index")),
                )
            )
        payload = EditedTranscript(
            markdown=markdown,
            sources=value.get("sources", []) or [],
            alignment=normalized_alignment,
            transcript_hash=value.get("transcript_hash"),
            markdown_hash=value.get("markdown_hash") or (compute_markdown_hash(markdown) if markdown else None),
            aligned_at=value.get("aligned_at"),
        )
        return payload.model_dump(mode="json")

    raise ValueError("edited_transcript must be an object (or legacy list)")


def edited_transcript_markdown(value: Any) -> str:
    if not value:
        return ""
    try:
        normalized = normalize_edited_transcript_payload(value)
    except ValueError:
        return ""
    return str(normalized.get("markdown") or "")


def normalize_sources_by_paragraph_count(
    sources: Any, paragraph_count: int
) -> list[list[dict[str, Any]]]:
    rows = sources if isinstance(sources, list) else []
    normalized: list[list[dict[str, Any]]] = []
    for row in rows[:paragraph_count]:
        if isinstance(row, list):
            normalized.append([item for item in row if isinstance(item, dict)])
        else:
            normalized.append([])
    while len(normalized) < paragraph_count:
        normalized.append([])
    return normalized


def build_alignment_rows(
    transcript: list[dict[str, Any]] | list[Segment],
    paragraphs: list[str],
) -> list[dict[str, Any]]:
    if not transcript or not paragraphs:
        return []
    transcript_texts = [
        seg["text"] if isinstance(seg, dict) else seg.text for seg in transcript
    ]
    aligned = align_dp_texts(transcript=transcript_texts, edited=paragraphs)
    rows: list[dict[str, Any]] = []
    for row in aligned:
        start_index = row.get("source_start_index")
        end_index = row.get("source_end_index")
        start = None
        end = None
        if (
            isinstance(start_index, int)
            and isinstance(end_index, int)
            and 0 <= start_index <= end_index < len(transcript)
        ):
            start_seg = transcript[start_index]
            end_seg = transcript[end_index]
            start = (
                float(start_seg["start"])
                if isinstance(start_seg, dict)
                else float(start_seg.start)
            )
            end = (
                float(end_seg["end"])
                if isinstance(end_seg, dict)
                else float(end_seg.end)
            )

        rows.append(
            {
                "start": start,
                "end": end,
                "match_score": float(row.get("match_score", 0.0)),
                "start_index": start_index,
                "end_index": end_index,
            }
        )
    return rows


def build_edited_transcript_payload(
    markdown: str,
    transcript: list[dict[str, Any]] | list[Segment],
    sources: Any = None,
    aligned_at_iso: str | None = None,
) -> dict[str, Any]:
    paragraphs = markdown_to_paragraphs(markdown)
    if not paragraphs and markdown.strip():
        paragraphs = [markdown.strip()]
    alignment = build_alignment_rows(transcript=transcript, paragraphs=paragraphs)
    return {
        "markdown": markdown,
        "sources": normalize_sources_by_paragraph_count(sources, len(paragraphs)),
        "alignment": alignment,
        "transcript_hash": compute_transcript_hash(transcript) if transcript else None,
        "markdown_hash": compute_markdown_hash(markdown) if markdown else None,
        "aligned_at": aligned_at_iso or datetime.utcnow().isoformat(),
    }

