"""Migrate legacy app_config payload to current schema.

Usage:
  - Dry-run (default): python backend/scripts/migrate_legacy_config.py
  - Apply changes:      python backend/scripts/migrate_legacy_config.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

import config as config_service
from database import create_db_and_tables, engine
from models import AppConfig


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_config_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    normalized = config_service._migrate_legacy_brief_config(normalized)
    normalized = config_service._migrate_summary_prompt_model_presets(normalized)
    normalized = config_service._migrate_correction_prompt_model_presets(normalized)
    normalized = config_service._migrate_edition_prompt_model_presets(normalized)
    normalized = config_service._migrate_extraction_prompt_model_presets(normalized)
    normalized = config_service._migrate_sources_prompt_model_presets(normalized)
    normalized = config_service.merge_dicts(config_service.DEFAULT_CONFIG.copy(), normalized)
    normalized = config_service._normalize_summary_prompt_limits(normalized)
    normalized = config_service._normalize_correction_prompt_limits(normalized)
    normalized = config_service._normalize_edition_prompt_limits(normalized)
    normalized = config_service._normalize_extraction_prompt_limits(normalized)
    normalized = config_service._normalize_sources_prompt_limits(normalized)
    normalized = config_service._normalize_brief_config(normalized)
    normalized = config_service._normalize_alignment_config(normalized)
    normalized = config_service._normalize_rag_config(normalized)
    normalized = config_service._sanitize_config(normalized)
    return normalized


def run_migration(apply: bool) -> int:
    create_db_and_tables()

    with Session(engine) as session:
        record = session.get(AppConfig, config_service.CONFIG_RECORD_ID)
        if record is None:
            print("No app_config row found (id=1). Nothing to migrate.")
            return 0

        current = record.data if isinstance(record.data, dict) else {}
        migrated = _normalize_config_payload(current)

        if _canonical(current) == _canonical(migrated):
            print("Config is already up-to-date. No changes required.")
            return 0

        print("Detected legacy config differences.")
        print(f"- keys before: {sorted(current.keys())}")
        print(f"- keys after : {sorted(migrated.keys())}")

        if not apply:
            print("Dry-run mode: no changes written. Re-run with --apply to persist.")
            return 0

        record.data = migrated
        session.add(record)
        session.commit()
        print("Migration applied to app_config (id=1).")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy app_config payload to current schema.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag, script runs as dry-run.",
    )
    args = parser.parse_args()
    return run_migration(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
