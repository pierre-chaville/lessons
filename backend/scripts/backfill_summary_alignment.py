"""One-shot backfill for summary <-> edited alignment metadata.

Usage:
  - Dry-run (default): python backend/scripts/backfill_summary_alignment.py
  - Apply changes:      python backend/scripts/backfill_summary_alignment.py --apply
  - Single lesson:      python backend/scripts/backfill_summary_alignment.py --lesson-id 123 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from database import create_db_and_tables, engine
from models import Lesson
from services.edited_transcript import (
    compute_markdown_hash,
    edited_transcript_markdown,
)
from services.summary_alignment import build_summary_alignment_metadata


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_effectively_null_json(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "null"}:
        return True
    return False


def _is_effectively_empty_text(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build_backfilled_metadata(
    lesson: Lesson,
    summary_min_alignment_score: float,
    force_realign: bool,
) -> tuple[dict[str, Any], bool]:
    summary_markdown = str(lesson.summary or "").strip()
    edited_markdown = edited_transcript_markdown(lesson.edited_transcript).strip()
    current_metadata = _as_dict(lesson.summary_metadata)

    summary_hash = compute_markdown_hash(summary_markdown) if summary_markdown else None
    edited_hash = compute_markdown_hash(edited_markdown) if edited_markdown else None
    current_alignment = current_metadata.get("summary_alignment")

    alignment_needs_refresh = force_realign or (
        current_metadata.get("summary_hash") != summary_hash
        or current_metadata.get("edited_markdown_hash") != edited_hash
        or not isinstance(current_alignment, list)
    )

    if alignment_needs_refresh:
        refreshed = build_summary_alignment_metadata(
            summary_markdown=summary_markdown,
            edited_markdown=edited_markdown,
            min_alignment_score=summary_min_alignment_score,
        )
        merged = {**current_metadata, **refreshed}
    else:
        merged = current_metadata

    changed = _canonical(merged) != _canonical(current_metadata)
    return merged, changed


def run_backfill(
    apply: bool,
    lesson_id: int | None,
    limit: int | None,
    force_realign: bool,
) -> int:
    create_db_and_tables()
    changed_count = 0
    checked_count = 0

    alignment_config = load_config().get("alignment", {})
    try:
        summary_min_alignment_score = float(
            alignment_config.get("summary_min_score", 0.2)
        )
    except (TypeError, ValueError):
        summary_min_alignment_score = 0.2
    summary_min_alignment_score = max(0.0, min(1.0, summary_min_alignment_score))

    with Session(engine) as session:
        statement = select(Lesson).where(
            Lesson.summary.isnot(None),
            Lesson.edited_transcript.isnot(None),
        )
        if lesson_id is not None:
            statement = statement.where(Lesson.id == lesson_id)
        rows = list(session.exec(statement).all())
        if limit is not None and limit > 0:
            rows = rows[:limit]

        print(
            f"Found {len(rows)} lesson(s) with summary + edited_transcript. "
            f"(summary_min_score={summary_min_alignment_score})"
        )
        for lesson in rows:
            if _is_effectively_empty_text(lesson.summary):
                print(f"[lesson {lesson.id}] skipped (summary is empty)")
                continue
            if _is_effectively_null_json(lesson.edited_transcript):
                print(f"[lesson {lesson.id}] skipped (edited_transcript is null)")
                continue
            if not edited_transcript_markdown(lesson.edited_transcript).strip():
                print(f"[lesson {lesson.id}] skipped (edited markdown is empty)")
                continue

            checked_count += 1
            try:
                metadata, changed = _build_backfilled_metadata(
                    lesson=lesson,
                    summary_min_alignment_score=summary_min_alignment_score,
                    force_realign=force_realign,
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

            lesson.summary_metadata = metadata
            session.add(lesson)
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
        description="Backfill summary <-> edited alignment metadata."
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
        help="Recompute alignment even when hashes look current.",
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

