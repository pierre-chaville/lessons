"""One-shot backfill for edited transcript alignment/hash metadata.

Usage:
  - Dry-run (default): python backend/scripts/backfill_edited_alignment.py
  - Apply changes:      python backend/scripts/backfill_edited_alignment.py --apply
  - Single lesson:      python backend/scripts/backfill_edited_alignment.py --lesson-id 123 --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import create_db_and_tables, engine
from models import Lesson
from models.versioning import ContentType, VersionSource
from services.dp_align_core import align_dp_texts
from services.edited_transcript import (
    compute_markdown_hash,
    compute_transcript_hash,
    markdown_to_paragraphs,
    normalize_edited_transcript_payload,
)
from services.versioning import update_content


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _source_transcript(lesson: Lesson) -> list[dict[str, Any]]:
    transcript = lesson.corrected_transcript or lesson.transcript or []
    out: list[dict[str, Any]] = []
    for seg in transcript:
        if isinstance(seg, dict):
            out.append(
                {
                    "start": float(seg.get("start", 0.0)),
                    "end": float(seg.get("end", 0.0)),
                    "text": str(seg.get("text", "")),
                }
            )
        else:
            out.append(
                {
                    "start": float(getattr(seg, "start", 0.0)),
                    "end": float(getattr(seg, "end", 0.0)),
                    "text": str(getattr(seg, "text", "")),
                }
            )
    return out


def _paragraphs_from_markdown(markdown: str) -> list[str]:
    paras = markdown_to_paragraphs(markdown)
    if not paras and markdown.strip():
        paras = [markdown.strip()]
    return paras


def _sources_for_paragraph_count(
    sources: Any, paragraph_count: int
) -> list[list[dict[str, Any]]]:
    rows = sources if isinstance(sources, list) else []
    normalized: list[list[dict[str, Any]]] = []
    for row in rows[:paragraph_count]:
        if isinstance(row, list):
            normalized.append([s for s in row if isinstance(s, dict)])
        else:
            normalized.append([])
    while len(normalized) < paragraph_count:
        normalized.append([])
    return normalized


def _build_alignment_rows(
    transcript: list[dict[str, Any]], paragraphs: list[str]
) -> list[dict[str, Any]]:
    if not transcript or not paragraphs:
        return []
    transcript_texts = [seg["text"] for seg in transcript]
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
            start = float(transcript[start_index]["start"])
            end = float(transcript[end_index]["end"])
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


def _build_backfilled_payload(
    lesson: Lesson, force_realign: bool
) -> tuple[dict[str, Any], bool]:
    current = normalize_edited_transcript_payload(lesson.edited_transcript)
    markdown = str(current.get("markdown", ""))
    paragraphs = _paragraphs_from_markdown(markdown)
    transcript = _source_transcript(lesson)
    transcript_hash = compute_transcript_hash(transcript) if transcript else None
    markdown_hash = compute_markdown_hash(markdown) if markdown else None

    current_alignment = current.get("alignment", []) or []
    alignment_needs_refresh = force_realign or (
        current.get("transcript_hash") != transcript_hash
        or current.get("markdown_hash") != markdown_hash
        or len(current_alignment) != len(paragraphs)
    )

    alignment = (
        _build_alignment_rows(transcript=transcript, paragraphs=paragraphs)
        if alignment_needs_refresh
        else current_alignment
    )
    aligned_at = (
        _now_iso_utc() if alignment_needs_refresh else current.get("aligned_at")
    )

    payload = {
        "markdown": markdown,
        "sources": _sources_for_paragraph_count(
            current.get("sources"), paragraph_count=len(paragraphs)
        ),
        "alignment": alignment,
        "transcript_hash": transcript_hash,
        "markdown_hash": markdown_hash,
        "aligned_at": aligned_at,
    }
    changed = _canonical(payload) != _canonical(current)
    return payload, changed


def _is_effectively_null_json(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "null"}:
        return True
    return False


def run_backfill(
    apply: bool,
    lesson_id: int | None,
    limit: int | None,
    force_realign: bool,
) -> int:
    create_db_and_tables()
    changed_count = 0
    checked_count = 0

    with Session(engine) as session:
        statement = select(Lesson).where(Lesson.edited_transcript.isnot(None))
        if lesson_id is not None:
            statement = statement.where(Lesson.id == lesson_id)
        rows = list(session.exec(statement).all())
        if limit is not None and limit > 0:
            rows = rows[:limit]

        print(f"Found {len(rows)} lesson(s) with edited_transcript.")
        for lesson in rows:
            if _is_effectively_null_json(lesson.edited_transcript):
                print(f"[lesson {lesson.id}] skipped (edited_transcript is null)")
                continue
            checked_count += 1
            try:
                payload, changed = _build_backfilled_payload(
                    lesson=lesson, force_realign=force_realign
                )
            except Exception as exc:
                print(f"[lesson {lesson.id}] ERROR: {exc}")
                continue

            if not changed:
                print(f"[lesson {lesson.id}] up-to-date")
                continue

            changed_count += 1
            if not apply:
                print(f"[lesson {lesson.id}] would update (dry-run)")
                continue

            update_content(
                session=session,
                lesson_id=lesson.id,
                content_type=ContentType.EDITED_TRANSCRIPT,
                new_content=payload,
                actor=None,
                source=VersionSource.PIPELINE,
                change_summary="Backfill edited transcript alignment metadata",
            )
            session.commit()
            print(f"[lesson {lesson.id}] updated")

    mode = "APPLY" if apply else "DRY-RUN"
    print(
        f"\n{mode} completed: checked={checked_count}, "
        f"changed={changed_count}, updated={changed_count if apply else 0}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill edited transcript alignment/hash metadata."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag, script runs as dry-run.",
    )
    parser.add_argument(
        "--lesson-id",
        type=int,
        default=None,
        help="Restrict backfill to one lesson id.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of lessons to process (after filters).",
    )
    parser.add_argument(
        "--force-realign",
        action="store_true",
        help="Recompute alignment even when hashes/length look current.",
    )
    args = parser.parse_args()

    return run_backfill(
        apply=args.apply,
        lesson_id=args.lesson_id,
        limit=args.limit,
        force_realign=args.force_realign,
    )


if __name__ == "__main__":
    raise SystemExit(main())

