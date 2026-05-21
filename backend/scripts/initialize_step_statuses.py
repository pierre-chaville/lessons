"""Initialize lesson step_statuses from existing lesson content.

Rules:
  - If a step has already been performed based on current data, set it to "in_progress".
  - Otherwise, set it to "non_started".

Usage:
  - Dry-run (default): python backend/scripts/initialize_step_statuses.py
  - Apply changes:      python backend/scripts/initialize_step_statuses.py --apply
  - Single lesson:      python backend/scripts/initialize_step_statuses.py --lesson-id 123 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

import crud
from database import create_db_and_tables, engine
from models import Lesson
from services.edited_transcript import edited_transcript_markdown
from services.lessons import normalize_step_statuses


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _has_transcript(lesson: Lesson) -> bool:
    return bool(isinstance(lesson.transcript, list) and len(lesson.transcript) > 0)


def _has_corrected_transcript(lesson: Lesson) -> bool:
    return bool(
        isinstance(lesson.corrected_transcript, list)
        and len(lesson.corrected_transcript) > 0
    )


def _has_edited_transcript(lesson: Lesson) -> bool:
    return bool(edited_transcript_markdown(lesson.edited_transcript).strip())


def _has_summary(lesson: Lesson) -> bool:
    return bool(isinstance(lesson.summary, str) and lesson.summary.strip())


def _has_brief(lesson: Lesson) -> bool:
    return bool(isinstance(lesson.brief, str) and lesson.brief.strip())


def _build_initialized_statuses(lesson: Lesson, session: Session) -> dict[str, str]:
    current = lesson.step_statuses if isinstance(lesson.step_statuses, dict) else {}
    # Preserve existing valid/legacy statuses (including migrated legacy keys),
    # then only fill missing non-started steps from content evidence.
    statuses = normalize_step_statuses(current)

    lesson_sources = crud.get_lesson_sources(session, lesson.id)
    has_extracted_sources = len(lesson_sources) > 0
    has_verified_sources = any(
        (
            source.verification_status is not None
            or source.verification_confidence is not None
            or source.verification_explanation is not None
            or source.slug_retrieved is not None
        )
        for source in lesson_sources
    )

    if statuses["transcription"] == "non_started" and _has_transcript(lesson):
        statuses["transcription"] = "in_progress"
    edited_inferred_done = (
        _has_corrected_transcript(lesson)
        or _has_edited_transcript(lesson)
        # Historical process pipeline states beyond edition imply edited exists.
        or (lesson.process_status in {"edition", "sources_extraction", "sources_checking", "summary"})
        # Summary/brief typically require edited content.
        or _has_summary(lesson)
        or _has_brief(lesson)
        # Metadata persisted for edited operations is also a strong signal.
        or bool(isinstance(lesson.edited_metadata, dict) and lesson.edited_metadata)
    )
    if statuses["edited"] == "non_started" and edited_inferred_done:
        statuses["edited"] = "in_progress"
    if statuses["sources"] == "non_started" and has_verified_sources:
        statuses["sources"] = "in_progress"
    elif statuses["sources"] == "non_started" and has_extracted_sources:
        statuses["sources"] = "in_progress"
    if statuses["summary"] == "non_started" and _has_summary(lesson):
        statuses["summary"] = "in_progress"
    if statuses["brief"] == "non_started" and _has_brief(lesson):
        statuses["brief"] = "in_progress"

    return statuses


def run_initialization(apply: bool, lesson_id: int | None, limit: int | None) -> int:
    create_db_and_tables()
    checked_count = 0
    changed_count = 0

    with Session(engine) as session:
        statement = select(Lesson).order_by(Lesson.id)
        if lesson_id is not None:
            statement = statement.where(Lesson.id == lesson_id)
        rows = list(session.exec(statement).all())
        if limit is not None and limit > 0:
            rows = rows[:limit]

        print(f"Found {len(rows)} lesson(s) to initialize.")
        for lesson in rows:
            checked_count += 1
            target = _build_initialized_statuses(lesson, session)
            current = lesson.step_statuses if isinstance(lesson.step_statuses, dict) else {}
            current_normalized = normalize_step_statuses(current)

            if _canonical(current_normalized) == _canonical(target):
                print(f"[lesson {lesson.id}] up-to-date")
                continue

            changed_count += 1
            if not apply:
                print(f"[lesson {lesson.id}] would update (dry-run)")
                continue

            lesson.step_statuses = target
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
        description="Initialize lesson step_statuses from existing data."
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
        help="Restrict initialization to one lesson id.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of lessons to process (after filters).",
    )
    args = parser.parse_args()
    return run_initialization(
        apply=args.apply,
        lesson_id=args.lesson_id,
        limit=args.limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())

