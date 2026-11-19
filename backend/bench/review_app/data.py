"""Data of the review app, read from the campaign files, the dataset and results/bench.sqlite.

The jobs of a campaign are planned like `bench.run` does (same cache keys), so the app shows
exactly the generations and scores the campaign would use. A campaign is loaded once and reloaded
when its config file or the database changes.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Optional

import yaml

from bench.dataset import BENCH_DIR, _format_seconds, format_transcript, load_dataset
from bench.db import BenchDB, options_json
from bench.metrics import get_metric_module
from bench.review_app.correction_diff import Comparator
from bench.review_app.metrics_table import aggregate, baseline_row
from bench.review_app.metrics_table import columns as metric_columns
from bench.run import Planner, gold_input, load_config, step_tasks
from bench.score import REFERENCE_FILES, metric_specs, reference_text

CONFIG_DIR = BENCH_DIR / "configs"
INPUT_FILES = {"correction": "initial.md", "edition": "corrected.md", "summary": "edited.md"}
SATURATION_RATE = 0.95  # idea_coverage: share of present ideas above which the metric no longer discriminates


class NotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Campaign loading
# --------------------------------------------------------------------------- #


def campaign_files() -> list[Path]:
    """Campaign configs: YAML files of configs/ with `models` and `steps` (gold configs excluded)."""
    files = []
    for path in sorted(CONFIG_DIR.glob("*.y*ml")):
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(config, dict) and config.get("models") and config.get("steps"):
            files.append(path)
    return files


def _db_path(config: dict) -> Path:
    return BENCH_DIR / config.get("output_db", "results/bench.sqlite")


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _db_signature(path: Path) -> tuple[float, float]:
    return _mtime(path), _mtime(path.with_name(path.name + "-wal"))


def open_db(path: Path) -> Optional[BenchDB]:
    return BenchDB.open_existing(path)


@dataclass
class Campaign:
    stem: str
    path: Path
    config: dict
    items: list[Any]
    jobs: list[Any]
    db_path: Path
    signature: tuple

    @property
    def name(self) -> str:
        return (self.config.get("campaign") or {}).get("name", self.stem)

    def step(self, name: str) -> dict:
        if name not in (self.config.get("steps") or {}):
            raise NotFound(f"unknown step {name!r}")
        return self.config["steps"][name]

    def step_jobs(self, name: str) -> list[Any]:
        self.step(name)
        return [j for j in self.jobs if j.step == name]


_cache: dict[str, Campaign] = {}
_lock = threading.Lock()


def load_campaign(stem: str) -> Campaign:
    path = next((p for p in campaign_files() if p.stem == stem), None)
    if path is None:
        raise NotFound(f"unknown campaign {stem!r}")
    config = load_config(path)
    db_path = _db_path(config)
    signature = (_mtime(path), *_db_signature(db_path))
    with _lock:
        cached = _cache.get(stem)
        if cached and cached.signature == signature:
            return cached
        steps = list(config.get("steps") or {})
        items, _ = load_dataset(config, step_tasks(config, steps))
        items = [i for i in items if not any(issue.level == "error" for issue in i.issues)]
        db = open_db(db_path)
        try:
            jobs, _ = Planner(config, items, db).plan(steps, None, None)
        finally:
            if db:
                db.close()
        campaign = Campaign(stem, path, config, items, jobs, db_path, signature)
        _cache[stem] = campaign
        return campaign


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def candidate_key(job) -> str:
    return f"{job.model_alias}|{job.prompt_name}"


def _candidates(jobs: list[Any]) -> list[dict]:
    seen: dict[str, dict] = {}
    for job in jobs:
        seen.setdefault(candidate_key(job), {
            "key": candidate_key(job), "model": job.model_alias, "prompt": job.prompt_name,
            "model_id": job.model_id, "provider": job.provider,
        })
    return list(seen.values())


def _column_meta(step: dict) -> list[dict]:
    meta = []
    for metric, options, column in metric_columns(step):
        module = get_metric_module(metric)
        meta.append({
            "metric": metric, "options": options_json(options), "label": column.label,
            "detail": column.label != metric, "higher_is_better": column.higher_is_better,
            "percent": column.percent, "digits": column.digits, "judge": bool(getattr(module, "JUDGE", False)),
        })
    return meta


def _scores(db: Optional[BenchDB], generation_ids: list[int]) -> dict[tuple[int, str, str], tuple[Optional[float], dict]]:
    if db is None:
        return {}
    return {
        (row["generation_id"], row["metric"], row["options"]): (row["value"], json.loads(row["details"] or "{}"))
        for row in db.scores(generation_ids)
    }


def _runs(db: Optional[BenchDB], campaign: Campaign) -> list[dict]:
    if db is None:
        return []
    rows = db.conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    runs = []
    for row in rows:
        if Path(row["config_path"]).stem != campaign.stem:
            continue
        runs.append({k: row[k] for k in ("id", "status", "started_at", "finished_at", "estimated_usd", "actual_usd",
                                         "dataset_version", "git_commit")})
    return runs


def _judge_cost(scores: dict) -> float:
    return sum((details.get("judge_cost_usd") or 0.0) for _, details in scores.values())


# --------------------------------------------------------------------------- #
# API payloads
# --------------------------------------------------------------------------- #


def campaigns_list() -> list[dict]:
    result = []
    for path in campaign_files():
        config = load_config(path)
        campaign_meta = config.get("campaign") or {}
        steps = config.get("steps") or {}
        db = open_db(_db_path(config))
        last_run = None
        try:
            if db is not None:
                for row in db.conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall():
                    if Path(row["config_path"]).stem == path.stem:
                        last_run = {"id": row["id"], "status": row["status"], "started_at": row["started_at"],
                                    "actual_usd": row["actual_usd"]}
                        break
        finally:
            if db:
                db.close()
        dataset = config.get("dataset") or {}
        result.append({
            "stem": path.stem,
            "name": campaign_meta.get("name", path.stem),
            "description": campaign_meta.get("description") or "",
            "dataset_version": config.get("dataset_version"),
            "lessons": sum(len(v or []) for v in dataset.values()) if isinstance(dataset, dict) else None,
            "steps": [{"name": n, "task": (s or {}).get("task", n), "models": len((s or {}).get("models") or [])}
                      for n, s in steps.items()],
            "models": list(config.get("models") or {}),
            "last_run": last_run,
            "modified": _mtime(path),
        })
    result.sort(key=lambda c: c["modified"], reverse=True)
    return result


def step_summary(campaign: Campaign, step_name: str, db: Optional[BenchDB]) -> dict:
    """The table of the HTML report as data: one row per model x prompt, mean ± spread per column."""
    step = campaign.step(step_name)
    jobs = campaign.step_jobs(step_name)
    columns = metric_columns(step)
    ids = [j.cached_id for j in jobs if j.cached_id is not None]
    scores = _scores(db, ids)
    generations = {gid: db.generation(gid) for gid in ids} if db else {}
    groups: dict[str, list[Any]] = defaultdict(list)
    for job in jobs:
        groups[candidate_key(job)].append(job)
    rows = []
    for key, group in groups.items():
        cells = []
        for metric, options, column in columns:
            by_lesson: dict[str, list[float]] = defaultdict(list)
            for job in group:
                score = scores.get((job.cached_id, metric, options_json(options)))
                if score is None:
                    continue
                number = column.extract(*score)
                if number is not None:
                    by_lesson[job.item.id].append(number)
            value, spread = aggregate(by_lesson)
            cells.append({"value": value, "spread": spread})
        ok = [generations[j.cached_id] for j in group if j.cached_id is not None]
        group_scores = {k: v for k, v in scores.items() if k[0] in {j.cached_id for j in group}}
        rows.append({
            "key": key, "model": group[0].model_alias, "prompt": group[0].prompt_name, "cells": cells,
            "calls_ok": len(ok), "calls": len(group), "lessons": len({j.item.id for j in group}),
            "cost_per_call": mean(g["cost_usd"] or 0 for g in ok) if ok else None,
            "latency": mean(g["latency_s"] or 0 for g in ok) if ok else None,
            "cost": sum(g["cost_usd"] or 0 for g in ok),
            "judge_cost": _judge_cost(group_scores),
        })
    baseline = baseline_row(jobs, columns)
    task = jobs[0].task if jobs else step.get("task", step_name)
    warnings = []
    for index, (metric, _, column) in enumerate(columns):
        if metric == "idea_coverage" and column.label == "present_rate":
            rates = [r["cells"][index]["value"] for r in rows if r["cells"][index]["value"] is not None]
            if len(rates) >= 2 and min(rates) >= SATURATION_RATE:
                warnings.append(f"idea_coverage looks saturated: every model has ≥ {SATURATION_RATE:.0%} of the "
                                "ideas present. Tighten the definition of the ideas or rely more on pairwise comparisons.")
    return {
        "name": step_name,
        "task": task,
        "columns": _column_meta(step),
        "rows": rows,
        "baseline": {"label": baseline[0], "cells": [{"value": v, "spread": s} for v, s in baseline[1]]}
        if baseline else None,
        "warnings": warnings,
        "failures": [
            {"label": j.label(), "error": (db.last_failure(j.cache_key)["error"]
                                           if db and j.input_text is not None and db.last_failure(j.cache_key)
                                           else "not generated")}
            for j in jobs if j.cached_id is None
        ],
    }


def dashboard(stem: str) -> dict:
    campaign = load_campaign(stem)
    db = open_db(campaign.db_path)
    try:
        steps = [step_summary(campaign, name, db) for name in campaign.config["steps"]]
        runs = _runs(db, campaign)
    finally:
        if db:
            db.close()
    meta = campaign.config.get("campaign") or {}
    judge = campaign.config.get("judge") or {}
    used = {j.model_alias for j in campaign.jobs}
    return {
        "stem": stem,
        "name": campaign.name,
        "description": meta.get("description") or "",
        "dataset_version": campaign.config.get("dataset_version"),
        "file": campaign.path.relative_to(BENCH_DIR).as_posix(),
        "lessons": [{"id": i.id, "kind": i.kind} for i in campaign.items],
        "models": {alias: {"id": m.get("id"), "provider": m.get("provider"), "params": m.get("params") or {}}
                   for alias, m in (campaign.config.get("models") or {}).items() if alias in used},
        "judge": {"model": judge.get("model"), "provider": judge.get("provider")} if judge else None,
        "steps": steps,
        "runs": runs,
        "cost": sum(r["cost"] for s in steps for r in s["rows"]),
        "judge_cost": sum(r["judge_cost"] for s in steps for r in s["rows"]),
    }


def step_detail(stem: str, step_name: str) -> dict:
    """Step summary + one row per lesson: per candidate, the metric values (mean over repeats)."""
    campaign = load_campaign(stem)
    db = open_db(campaign.db_path)
    try:
        summary = step_summary(campaign, step_name, db)
        jobs = campaign.step_jobs(step_name)
        columns = metric_columns(campaign.step(step_name))
        scores = _scores(db, [j.cached_id for j in jobs if j.cached_id is not None])
    finally:
        if db:
            db.close()
    lessons = []
    for item in campaign.items:
        lesson_jobs = [j for j in jobs if j.item.id == item.id]
        if not lesson_jobs:
            continue
        by_candidate: dict[str, list[Any]] = defaultdict(list)
        for job in lesson_jobs:
            by_candidate[candidate_key(job)].append(job)
        values = {}
        for key, group in by_candidate.items():
            cells = []
            for metric, options, column in columns:
                numbers = []
                for job in group:
                    score = scores.get((job.cached_id, metric, options_json(options)))
                    if score is not None and (n := column.extract(*score)) is not None:
                        numbers.append(n)
                cells.append(mean(numbers) if numbers else None)
            values[key] = {"cells": cells, "ok": sum(j.cached_id is not None for j in group), "calls": len(group)}
        lessons.append({"id": item.id, "kind": item.kind, "values": values})
    return {**summary, "campaign": campaign.name, "candidates": _candidates(jobs), "lessons": lessons}


def _correction_rows(item, outputs: dict[str, str], case_sensitive: bool) -> list[dict]:
    from bench.dataset import parse_transcript

    compare = Comparator(case_sensitive)
    initial = {(s.start, s.end): s.text for s in item.initial or []}
    parsed = {}
    for key, text in outputs.items():
        segments, _ = parse_transcript(text)
        parsed[key] = {(s.start, s.end): s.text for s in segments}
    rows = []
    for gold in item.corrected or []:
        span = (gold.start, gold.end)
        init_text = initial.get(span, "")
        init_sev = compare.severity(init_text, gold.text)
        cells = {}
        for key, segments in parsed.items():
            text = segments.get(span)
            if text is None:
                cells[key] = {"severity": "fold", "html": "<em>missing segment</em>"}
            else:
                severity = compare.severity(text, gold.text)
                cells[key] = {"severity": severity, "html": compare.highlight(text, gold.text) if severity else None,
                              "text": text}
        rows.append({
            "start": gold.start, "end": gold.end,
            "time": f"{_format_seconds(gold.start)} – {_format_seconds(gold.end)}",
            "gold": gold.text,
            "initial": {"severity": init_sev, "text": init_text,
                        "html": compare.highlight(init_text, gold.text) if init_sev else None},
            "cells": cells,
        })
    return rows


def lesson_detail(stem: str, step_name: str, lesson_id: str, candidates: Optional[list[str]] = None,
                  repeat: Optional[int] = None) -> dict:
    """Gold vs outputs of the selected candidates for one lesson (first successful repeat by default)."""
    campaign = load_campaign(stem)
    step = campaign.step(step_name)
    jobs = [j for j in campaign.step_jobs(step_name) if j.item.id == lesson_id]
    if not jobs:
        raise NotFound(f"no job for lesson {lesson_id!r} in step {step_name!r}")
    item = jobs[0].item
    task = jobs[0].task
    all_candidates = _candidates(campaign.step_jobs(step_name))
    selected = [c for c in (candidates or [c["key"] for c in all_candidates]) if c in {x["key"] for x in all_candidates}]
    repeats = sorted({j.repeat for j in jobs})

    db = open_db(campaign.db_path)
    try:
        chosen: dict[str, Any] = {}
        for job in sorted(jobs, key=lambda j: j.repeat):
            key = candidate_key(job)
            if key not in selected or key in chosen:
                continue
            if repeat is not None:
                if job.repeat == repeat:
                    chosen[key] = job
            elif job.cached_id is not None:
                chosen[key] = job
        for key in selected:  # no successful repeat: show the failure of the first one
            if key not in chosen:
                chosen[key] = next(j for j in sorted(jobs, key=lambda j: j.repeat)
                                   if candidate_key(j) == key and (repeat is None or j.repeat == repeat))
        ids = [j.cached_id for j in chosen.values() if j.cached_id is not None]
        scores = _scores(db, ids)
        outputs = []
        for key in selected:
            job = chosen[key]
            entry = {"key": key, "model": job.model_alias, "prompt": job.prompt_name, "repeat": job.repeat,
                     "generation_id": job.cached_id, "output": None, "error": None, "scores": []}
            if job.cached_id is not None and db is not None:
                row = db.generation(job.cached_id)
                entry.update(output=row["output"], tokens_in=row["tokens_in"], tokens_out=row["tokens_out"],
                             cost_usd=row["cost_usd"], latency_s=row["latency_s"], created_at=row["created_at"],
                             meta=json.loads(row["meta"] or "{}"))
                for metric, options in metric_specs(step):
                    score = scores.get((job.cached_id, metric, options_json(options)))
                    if score is not None:
                        entry["scores"].append({"metric": metric, "options": options, "value": score[0],
                                                "details": score[1]})
            else:
                failure = db.last_failure(job.cache_key) if db is not None and job.input_text is not None else None
                entry["error"] = failure["error"] if failure else "not generated"
            outputs.append(entry)
    finally:
        if db:
            db.close()

    input_text = jobs[0].input_text if jobs[0].input_text is not None else gold_input(task, item)
    result = {
        "campaign": campaign.name, "step": step_name, "task": task, "lesson": item.id, "meta": item.meta,
        "lessons": sorted({j.item.id for j in campaign.step_jobs(step_name)}),
        "candidates": all_candidates, "selected": selected, "repeats": repeats, "repeat": repeat,
        "columns": _column_meta(step),
        "input_file": INPUT_FILES.get(task), "gold_file": REFERENCE_FILES.get(task),
        "input": input_text, "gold": reference_text(task, item),
        "ideas": item.ideas, "keypoints": item.keypoints,
        "outputs": outputs,
    }
    if task == "correction":
        case_sensitive = bool((((campaign.config.get("report") or {}).get("correction_errors") or {})
                               .get("case_sensitive", True)))
        result["segments"] = _correction_rows(
            item, {o["key"]: o["output"] for o in outputs if o["output"] is not None}, case_sensitive)
        result["input"] = format_transcript(item.initial or [])
    return result
