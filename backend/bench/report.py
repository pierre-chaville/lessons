"""Minimal HTML report: one table per step comparing models x prompts across metrics."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Callable, Optional

from bench.db import BenchDB, options_json
from bench.metrics import get_metric_module
from bench.score import REFERENCE_FILES, metric_specs, reference_text

INPUT_BASELINE_LABEL = "input, unchanged"


@dataclass
class Column:
    label: str
    higher_is_better: Optional[bool]  # None: no best value (e.g. a length checked against a range)
    extract: Callable[[float, dict], Optional[float]]  # (value, details) -> number
    percent: bool = False
    digits: int = 3

    def format(self, value: Optional[float]) -> str:
        if value is None:
            return "–"
        return f"{value * 100:.2f}" if self.percent else f"{value:.{self.digits}f}"

    @property
    def arrow(self) -> str:
        return {True: " ↑", False: " ↓"}.get(self.higher_is_better, "")


def _columns(step: dict) -> list[tuple[str, dict, Column]]:
    """(metric, options, column) for the implemented metrics of a step, details columns included."""
    columns = []
    for name, options in metric_specs(step):
        try:
            module = get_metric_module(name)
        except KeyError:
            continue
        percent = getattr(module, "PERCENT", False)
        percent_details = getattr(module, "PERCENT_DETAILS", set(module.REPORT_DETAILS) if percent else set())
        digits = getattr(module, "DIGITS", 3)
        columns.append((name, options, Column(name, module.HIGHER_IS_BETTER, lambda v, d: v, percent, digits)))
        for key, higher in module.REPORT_DETAILS.items():
            columns.append((name, options, Column(
                key, higher, lambda v, d, key=key: d.get(key), key in percent_details, digits
            )))
    return columns


def _aggregate(values_by_lesson: dict[str, list[float]]) -> tuple[Optional[float], Optional[float]]:
    """Mean over lessons of the mean over repeats, and mean spread (std) between repeats."""
    lesson_means = [mean(v) for v in values_by_lesson.values() if v]
    spreads = [pstdev(v) for v in values_by_lesson.values() if len(v) >= 2]
    return (mean(lesson_means) if lesson_means else None), (mean(spreads) if spreads else None)


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


def _step_table(step_name: str, step: dict, jobs: list[Any], db: BenchDB, link: Optional[Path] = None) -> str:
    columns = _columns(step)
    generation_ids = [j.cached_id for j in jobs if j.cached_id is not None]
    # Scores computed with other options (e.g. before a change of the campaign) are ignored.
    scores: dict[tuple[int, str, str], tuple[Optional[float], dict]] = {}
    for row in db.scores(generation_ids):
        key = (row["generation_id"], row["metric"], row["options"])
        scores[key] = (row["value"], json.loads(row["details"] or "{}"))
    generations = {gid: db.generation(gid) for gid in generation_ids}

    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for job in jobs:
        groups[(job.model_alias, job.prompt_name)].append(job)

    rows = []  # (label cells, metric cells [(mean, spread)], extra cells, is_baseline)
    for (alias, prompt), group in groups.items():
        cells = []
        for metric, options, column in columns:
            by_lesson: dict[str, list[float]] = defaultdict(list)
            for job in group:
                key = (job.cached_id, metric, options_json(options))
                if job.cached_id is None or key not in scores:
                    continue
                value, details = scores[key]
                number = column.extract(value, details)
                if number is not None:
                    by_lesson[job.item.id].append(number)
            cells.append(_aggregate(by_lesson))
        ok = [generations[j.cached_id] for j in group if j.cached_id is not None]
        extra = [
            f"{len(ok)}/{len(group)}",
            str(len({j.item.id for j in group})),
            _fmt(mean(g["cost_usd"] or 0 for g in ok), 4) if ok else "–",
            _fmt(mean(g["latency_s"] or 0 for g in ok), 1) if ok else "–",
            _fmt(sum(g["cost_usd"] or 0 for g in ok), 4),
        ]
        rows.append(([alias, prompt], cells, extra, False))

    baseline = _baseline_row(jobs, columns)
    if baseline:
        rows.append(([baseline[0], ""], baseline[1], ["", "", "", "", ""], True))

    best: list[Optional[float]] = []
    for index, (_, _, column) in enumerate(columns):
        values = [r[1][index][0] for r in rows if not r[3] and r[1][index][0] is not None]
        if len(values) < 2 or column.higher_is_better is None:
            best.append(None)
        else:
            best.append(max(values) if column.higher_is_better else min(values))

    titles = {True: "higher is better", False: "lower is better", None: "no better direction"}
    head = "".join(
        f"<th title=\"{titles[c.higher_is_better]}\">{html.escape(c.label)}{' %' if c.percent else ''}{c.arrow}</th>"
        for _, _, c in columns
    )
    body = []
    for labels, cells, extra, is_baseline in rows:
        tds = [f"<td class='label'>{html.escape(x)}</td>" for x in labels]
        for index, (value, spread) in enumerate(cells):
            column = columns[index][2]
            text = column.format(value)
            if spread is not None:
                text += f" <span class='spread'>± {column.format(spread)}</span>"
            css = "best" if value is not None and value == best[index] else ""
            tds.append(f"<td class='{css}'>{text}</td>")
        tds += [f"<td>{html.escape(x)}</td>" for x in extra]
        body.append(f"<tr class='{'baseline' if is_baseline else ''}'>{''.join(tds)}</tr>")

    link_html = f"<p class='meta'><a href='{html.escape(link.name)}'>Errors segment by segment</a></p>" if link else ""
    return f"""
<h2>{html.escape(step_name)}</h2>{link_html}
<table>
  <thead><tr><th>model</th><th>prompt</th>{head}<th>calls ok</th><th>lessons</th>
  <th>USD / call</th><th>s / call</th><th>total USD</th></tr></thead>
  <tbody>{''.join(body)}</tbody>
</table>
{_failures(jobs, db)}"""


def _baseline_row(jobs: list[Any], columns) -> Optional[tuple[str, list[tuple[Optional[float], Optional[float]]]]]:
    """(label, cells) of the row scoring a non-model text with the same metrics:
    - correction: the input itself, i.e. what the model has to improve on;
    - edition / summary: the hand-made reference (edited.md / summary.md), i.e. the expected level.
    """
    if not jobs:
        return None
    task = jobs[0].task
    if task == "correction":
        label = INPUT_BASELINE_LABEL
    elif task in REFERENCE_FILES:
        label = f"reference ({REFERENCE_FILES[task]})"
    else:
        return None
    lessons = {}
    for job in jobs:
        if job.input_text is not None:
            lessons.setdefault(job.item.id, job)
    cells = []
    results: dict[tuple[str, str], Any] = {}
    for metric, options, column in columns:
        by_lesson: dict[str, list[float]] = defaultdict(list)
        for lesson_id, job in lessons.items():
            reference = reference_text(job.task, job.item)
            text = job.input_text if task == "correction" else reference
            if text is None:
                continue
            key = (lesson_id, metric)
            if key not in results:
                try:
                    results[key] = get_metric_module(metric).compute(
                        text, input_text=job.input_text, reference=reference, options=options,
                    )
                except Exception:
                    results[key] = None
            if results[key] is None:
                continue
            number = column.extract(results[key].value, results[key].details)
            if number is not None:
                by_lesson[lesson_id].append(number)
        cells.append(_aggregate(by_lesson))
    return label, cells


def _failures(jobs: list[Any], db: BenchDB) -> str:
    missing = [j for j in jobs if j.cached_id is None]
    if not missing:
        return ""
    items = []
    for job in missing:
        failure = db.last_failure(job.cache_key) if job.input_text is not None else None
        reason = failure["error"] if failure else "not generated"
        items.append(f"<li>{html.escape(job.label())}: <code>{html.escape(reason)}</code></li>")
    return f"<details><summary>{len(missing)} call(s) without output</summary><ul>{''.join(items)}</ul></details>"


def write_report(path: Path, *, config: dict, jobs: list[Any], db: BenchDB,
                 links: Optional[dict[str, Path]] = None) -> Path:
    """`links`: {step: path of a detail report in the same folder}."""
    campaign = config.get("campaign") or {}
    name = campaign.get("name", "campaign")
    run = db.last_run(name)
    run_info = "no run yet"
    if run:
        run_info = (f"#{run['id']} {run['status']} – started {run['started_at']} – "
                    f"commit {run['git_commit'] or '?'} – cost ${run['actual_usd'] or 0:.4f}")

    steps = config.get("steps") or {}
    sections = []
    for step_name in steps:
        step_jobs = [j for j in jobs if j.step == step_name]
        if step_jobs:
            sections.append(_step_table(step_name, steps[step_name], step_jobs, db, (links or {}).get(step_name)))

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Bench – {html.escape(name)}</title>
<style>
  :root {{ color-scheme: light dark; background: Canvas; color: CanvasText; }}
  body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
  h1 {{ margin-bottom: .2rem; }}
  .meta {{ opacity: .7; font-size: .9rem; margin: .1rem 0; }}
  table {{ border-collapse: collapse; margin: .5rem 0 1rem; font-size: .9rem; }}
  th, td {{ border: 1px solid rgba(128, 128, 128, .35); padding: .35rem .6rem; text-align: right; white-space: nowrap; }}
  th {{ background: rgba(128, 128, 128, .15); }}
  td.label {{ text-align: left; }}
  td.best {{ font-weight: bold; background: rgba(76, 175, 80, .22); }}
  tr.baseline td {{ opacity: .65; font-style: italic; background: rgba(128, 128, 128, .06); }}
  .spread {{ opacity: .6; font-size: .8rem; }}
  details {{ font-size: .85rem; margin-bottom: 1.5rem; }}
  a {{ color: LinkText; }}
</style></head><body>
<h1>{html.escape(name)}</h1>
<p class="meta">{html.escape(campaign.get('description') or '')}</p>
<p class="meta">Dataset {html.escape(str(config.get('dataset_version', '?')))} – last run {html.escape(run_info)}
 – report generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p class="meta">Values: mean over lessons of the mean over repeats; ± = mean spread (std) between repeats.
Best value per column in green (columns without ↑/↓ have no best value). Grey rows score a text
that is not a model output: "{INPUT_BASELINE_LABEL}" = the step input itself (correction),
"reference (…)" = the hand-made reference (edition, summary).</p>
{''.join(sections) or '<p>No generation for this campaign yet.</p>'}
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
