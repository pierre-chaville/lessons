"""Backfill missing content on legacy v1 backfill versions.

This script targets versions with:
  - version_number = 1
  - sealed_reason = "backfill"
  - content is null

and fills content from the current lesson cache columns.

Usage:
  - Dry-run (default): python backend/scripts/backfill_legacy_v1_versions.py
  - Apply changes:      python backend/scripts/backfill_legacy_v1_versions.py --apply
  - Single lesson:      python backend/scripts/backfill_legacy_v1_versions.py --lesson-id 123 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import create_db_and_tables, engine
from models import Lesson
from models.versioning import ContentType, ContentVersion
from services.edited_transcript import normalize_edited_transcript_payload


def _fallback_content(lesson: Lesson, content_type: ContentType) -> Any:
    if content_type == ContentType.TITLE:
        return lesson.title or ""
    if content_type == ContentType.BRIEF:
        return lesson.brief or ""
    if content_type == ContentType.SUMMARY:
        return lesson.summary or ""
    if content_type == ContentType.CORRECTED_TRANSCRIPT:
        return lesson.corrected_transcript or []
    if content_type == ContentType.EDITED_TRANSCRIPT:
        raw = lesson.edited_transcript if lesson.edited_transcript is not None else {"markdown": ""}
        try:
            return normalize_edited_transcript_payload(raw)
        except Exception:
            return {"markdown": ""}
    return None


def _query_candidates(session: Session, lesson_id: Optional[int]) -> list[ContentVersion]:
    statement = select(ContentVersion).where(
        ContentVersion.version_number == 1,
        ContentVersion.sealed_reason == "backfill",
    )
    if lesson_id is not None:
        statement = statement.where(ContentVersion.lesson_id == lesson_id)
    rows = list(session.exec(statement).all())
    return [row for row in rows if row.content is None]


def run_backfill(apply: bool, lesson_id: Optional[int], limit: Optional[int]) -> int:
    create_db_and_tables()

    inspected = 0
    candidate_count = 0
    updated_count = 0

    with Session(engine) as session:
        candidates = _query_candidates(session, lesson_id=lesson_id)
        if limit is not None and limit > 0:
            candidates = candidates[:limit]
        candidate_count = len(candidates)

        if candidate_count == 0:
            print("No legacy v1 backfill versions with null content found.")
            return 0

        print(f"Found {candidate_count} candidate version(s).")
        for version in candidates:
            inspected += 1
            lesson = session.get(Lesson, version.lesson_id)
            if lesson is None:
                print(f"[version {version.id}] skipped: lesson {version.lesson_id} not found")
                continue

            try:
                content_type = ContentType(version.content_type)
            except Exception:
                print(f"[version {version.id}] skipped: unsupported content_type={version.content_type}")
                continue

            replacement = _fallback_content(lesson, content_type)
            if replacement is None:
                print(f"[version {version.id}] skipped: no fallback available for {content_type.value}")
                continue

            if not apply:
                print(f"[version {version.id}] would backfill {content_type.value} (lesson {lesson.id})")
                continue

            version.content = replacement
            session.add(version)
            updated_count += 1
            print(f"[version {version.id}] backfilled {content_type.value} (lesson {lesson.id})")

        if apply and updated_count > 0:
            session.commit()

    mode = "APPLY" if apply else "DRY-RUN"
    print(
        f"\n{mode} completed: inspected={inspected}, candidates={candidate_count}, "
        f"updated={updated_count}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing content on legacy v1 backfill versions.")
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
        help="Max number of versions to process (after filters).",
    )
    args = parser.parse_args()
    return run_backfill(
        apply=args.apply,
        lesson_id=args.lesson_id,
        limit=args.limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
