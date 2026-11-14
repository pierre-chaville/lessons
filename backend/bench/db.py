"""SQLite storage of the bench results (see README "Runs and database")."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign        TEXT NOT NULL,
    config_path     TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    dataset_version TEXT,
    git_commit      TEXT,
    args            TEXT,              -- JSON: command line options
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,     -- running | completed | budget_exceeded | interrupted | failed
    estimated_usd   REAL,
    actual_usd      REAL
);

CREATE TABLE IF NOT EXISTS prompts (
    sha     TEXT PRIMARY KEY,
    path    TEXT NOT NULL,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES runs(id),
    cache_key           TEXT NOT NULL,
    lesson_id           TEXT NOT NULL,
    step                TEXT NOT NULL,
    task                TEXT NOT NULL,
    function            TEXT NOT NULL,
    version             TEXT NOT NULL,
    model_alias         TEXT NOT NULL,
    provider            TEXT,           -- openai | anthropic | openrouter (NULL: before the provider field)
    model_id            TEXT NOT NULL,
    params              TEXT NOT NULL,  -- JSON
    prompt_path         TEXT NOT NULL,
    prompt_sha          TEXT NOT NULL REFERENCES prompts(sha),
    input_source        TEXT NOT NULL,  -- raw | gold | pipeline
    input_sha           TEXT NOT NULL,
    input_generation_id INTEGER REFERENCES generations(id),
    repeat_index        INTEGER NOT NULL,
    output              TEXT,
    output_format       TEXT,           -- text | json
    tokens_in           INTEGER,
    tokens_out          INTEGER,
    cost_usd            REAL,
    latency_s           REAL,
    attempts            INTEGER NOT NULL,
    error               TEXT,           -- NULL = success
    meta                TEXT,           -- JSON: adapter diagnostics
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_generations_cache_key ON generations(cache_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_generations_success ON generations(cache_key) WHERE error IS NULL;
CREATE INDEX IF NOT EXISTS ix_generations_lesson_step ON generations(lesson_id, step, model_alias);

CREATE TABLE IF NOT EXISTS scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER NOT NULL REFERENCES generations(id),
    metric        TEXT NOT NULL,
    options       TEXT NOT NULL,        -- JSON: metric options of the campaign
    value         REAL,                 -- NULL = undefined
    details       TEXT,                 -- JSON
    judge_model   TEXT,                 -- NULL for deterministic metrics
    created_at    TEXT NOT NULL,
    UNIQUE (generation_id, metric, options)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def options_json(options: dict) -> str:
    """Metric options as stored in scores.options."""
    return _json(options)


class BenchDB:
    """Access to results/bench.sqlite. Not thread-safe: use it from the main thread only."""

    def __init__(self, path: Path, readonly: bool = False):
        self.path = path
        if readonly:
            self.conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            self._migrate()
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

    @classmethod
    def open_existing(cls, path: Path) -> Optional["BenchDB"]:
        """Read-only access, or None if the database does not exist yet."""
        return cls(path, readonly=True) if path.is_file() else None

    def _migrate(self) -> None:
        """Columns added after the first version of the schema."""
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(generations)")}
        if "provider" not in columns:
            self.conn.execute("ALTER TABLE generations ADD COLUMN provider TEXT")
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- runs ---------------------------------------------------------------

    def start_run(self, *, campaign: str, config_path: str, config_hash: str, dataset_version: Optional[str],
                  git_commit: Optional[str], args: dict, estimated_usd: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (campaign, config_path, config_hash, dataset_version, git_commit, args, "
            "started_at, status, estimated_usd, actual_usd) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, 0)",
            (campaign, config_path, config_hash, dataset_version, git_commit, _json(args), now(), estimated_usd),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, actual_usd: float) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, actual_usd = ? WHERE id = ?",
            (now(), status, actual_usd, run_id),
        )
        self.conn.commit()

    # -- generations --------------------------------------------------------

    def cached(self, cache_key: str) -> Optional[sqlite3.Row]:
        """Successful generation with this key, if any."""
        return self.conn.execute(
            "SELECT * FROM generations WHERE cache_key = ? AND error IS NULL", (cache_key,)
        ).fetchone()

    def generation(self, generation_id: int) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM generations WHERE id = ?", (generation_id,)).fetchone()

    def last_failure(self, cache_key: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM generations WHERE cache_key = ? AND error IS NOT NULL ORDER BY id DESC LIMIT 1",
            (cache_key,),
        ).fetchone()

    def last_run(self, campaign: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM runs WHERE campaign = ? ORDER BY id DESC LIMIT 1", (campaign,)
        ).fetchone()

    # -- scores -------------------------------------------------------------

    def upsert_score(self, generation_id: int, metric: str, options: dict, value: Optional[float],
                     details: dict, judge_model: Optional[str] = None) -> None:
        self.conn.execute(
            "INSERT INTO scores (generation_id, metric, options, value, details, judge_model, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (generation_id, metric, options) DO UPDATE SET "
            "value = excluded.value, details = excluded.details, judge_model = excluded.judge_model, "
            "created_at = excluded.created_at",
            (generation_id, metric, _json(options), value, _json(details), judge_model, now()),
        )

    def scores(self, generation_ids: list[int]) -> list[sqlite3.Row]:
        if not generation_ids:
            return []
        placeholders = ", ".join("?" for _ in generation_ids)
        return self.conn.execute(
            f"SELECT * FROM scores WHERE generation_id IN ({placeholders})", tuple(generation_ids)
        ).fetchall()

    def commit(self) -> None:
        self.conn.commit()

    def save_prompt(self, sha: str, path: str, content: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO prompts (sha, path, content) VALUES (?, ?, ?)", (sha, path, content))

    def add_generation(self, run_id: int, record: dict) -> int:
        record = dict(record, run_id=run_id, created_at=now())
        for key in ("params", "meta"):
            if not isinstance(record.get(key), (str, type(None))):
                record[key] = _json(record[key])
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        cur = self.conn.execute(f"INSERT INTO generations ({columns}) VALUES ({placeholders})", tuple(record.values()))
        self.conn.commit()
        return int(cur.lastrowid)
