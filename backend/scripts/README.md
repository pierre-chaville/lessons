# Backfill Scripts

These scripts are intended for one-shot maintenance operations on existing lessons.

## Edited Transcript Alignment

Rebuilds `edited_transcript` alignment/hash metadata from current edited markdown + transcript.

- Dry-run: `python backend/scripts/backfill_edited_alignment.py`
- Apply: `python backend/scripts/backfill_edited_alignment.py --apply`
- One lesson: `python backend/scripts/backfill_edited_alignment.py --lesson-id 123 --apply`
- Force recompute: `python backend/scripts/backfill_edited_alignment.py --force-realign --apply`

## Summary ↔ Edited Alignment

Rebuilds `summary_metadata` alignment/hash metadata from current summary + edited markdown.

- Dry-run: `python backend/scripts/backfill_summary_alignment.py`
- Apply: `python backend/scripts/backfill_summary_alignment.py --apply`
- One lesson: `python backend/scripts/backfill_summary_alignment.py --lesson-id 123 --apply`
- Force recompute: `python backend/scripts/backfill_summary_alignment.py --force-realign --apply`

## Notes

- Scripts are **dry-run by default**.
- Use `--limit N` on either script to process a subset first.
- Prefer running dry-run before apply in production-like environments.
