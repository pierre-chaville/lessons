"""HTML report of the correction errors, segment by segment.

One table per lesson: a row per segment where the initial transcript or at least one model differs
from corrected.md; columns: timestamps, initial, corrected, then one column per model x prompt
(first successful repeat). A model cell is empty when the model's segment matches corrected.md,
and shows the model text otherwise, colored by severity (red: wer_fold error, orange: wer_norm
error only, yellow: case / accents / apostrophes / hyphens only), differing words highlighted.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rapidfuzz.distance import Levenshtein

from bench.dataset import _format_seconds, format_transcript, parse_transcript
from bench.db import BenchDB
from bench.metrics import get_metric_module
from bench.score import metric_specs
from bench.metrics.text import WORD_LEVELS, strip_speaker_tag, tokenize

# Severity of a difference, from the least to the most important: "minor" = counted by wer only
# (case, accents, inner apostrophes / hyphens), "norm" = counted by wer_norm but not by wer_fold
# (transliteration variant), "fold" = still counted by wer_fold (real error).
SEVERITIES = ("minor", "norm", "fold")


class Comparator:
    """Compares texts with corrected.md, ignoring punctuation and spacing (case counts by default)."""

    def __init__(self, case_sensitive: bool = True):
        self.lowercase = not case_sensitive

    def words(self, text: str, severity: str = "minor") -> list[str]:
        """Words compared at a severity level: the words of the comparator for "minor", the words of
        wer_norm / wer_fold for "norm" / "fold"."""
        if severity == "minor":
            return tokenize(strip_speaker_tag(text), lowercase=self.lowercase)
        transform = WORD_LEVELS[severity]
        return [w for w in map(transform, tokenize(strip_speaker_tag(text))) if w]

    def same(self, text: str, gold: str) -> bool:
        return self.words(text) == self.words(gold)

    def severity(self, text: str, gold: str) -> Optional[str]:
        """Most important level at which `text` differs from `gold` (None if they are the same)."""
        for severity in reversed(SEVERITIES):
            if self.words(text, severity) != self.words(gold, severity):
                return severity
        return None

    def highlight(self, text: str, gold: str) -> str:
        """HTML of `text` with the words that differ from `gold` in <mark class="severity">, and a
        caret where gold words are missing. Each word gets the most important level at which it differs."""
        raw = text.split()
        marked: dict[int, str] = {}
        gaps: dict[int, str] = {}
        for severity in SEVERITIES:
            units = [(i, " ".join(self.words(w, severity))) for i, w in enumerate(raw)]
            units = [(i, u) for i, u in units if u]  # punctuation-only words are never marked
            for op in Levenshtein.opcodes([u for _, u in units], self.words(gold, severity)):
                if op.tag in ("replace", "delete"):
                    marked.update((units[k][0], severity) for k in range(op.src_start, op.src_end))
                elif op.tag == "insert":
                    gaps[units[op.src_start][0] if op.src_start < len(units) else len(raw)] = severity
        out = []
        for i, w in enumerate([*raw, ""]):
            if i in gaps:
                out.append(f"<mark class='{gaps[i]} gap' title='missing words'>‸</mark>")
            if w:
                out.append(f"<mark class='{marked[i]}'>{html.escape(w)}</mark>" if i in marked else html.escape(w))
        return " ".join(out)


def _model_outputs(jobs: list[Any], db: BenchDB) -> tuple[list[str], dict[str, dict[str, dict]], dict[str, dict[str, str]]]:
    """Columns (model / prompt labels), {lesson: {column: {(start, end): text}}} and
    {lesson: {column: raw output}} (first OK repeat)."""
    several_prompts = len({j.prompt_name for j in jobs}) > 1
    columns: list[str] = []
    outputs: dict[str, dict[str, dict]] = defaultdict(dict)
    raw: dict[str, dict[str, str]] = defaultdict(dict)
    for job in sorted(jobs, key=lambda j: j.repeat):
        column = f"{job.model_alias} / {job.prompt_name}" if several_prompts else job.model_alias
        if column not in columns:
            columns.append(column)
        if job.cached_id is None or column in outputs[job.item.id]:
            continue
        raw[job.item.id][column] = db.generation(job.cached_id)["output"] or ""
        segments, _ = parse_transcript(raw[job.item.id][column])
        outputs[job.item.id][column] = {(s.start, s.end): s.text for s in segments}
    return columns, outputs, raw


# Summary tables: (title, metric, (numerator key, denominator key) of the details, higher is better).
# The `all` column is sum(numerator) / sum(denominator) over the lessons.
METRIC_TABLES = (
    ("WER fold", "wer_fold", ("errors", "ref_length"), False),
    ("Hebrew term accuracy", "hebrew_term_accuracy", ("right", "terms"), True),
)


def _metric_table(title: str, metric: str, keys_ratio: tuple[str, str], higher_is_better: bool, options: dict,
                  lessons: dict[str, Any], columns: list[str], raw: dict[str, dict[str, str]]) -> str:
    """A metric per lesson and model (initial = input unchanged), with the options of the campaign.
    The best model of each column is in bold."""
    module = get_metric_module(metric)
    num_key, den_key = keys_ratio
    stats: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)  # {row: {lesson: (numerator, denominator)}}
    for lesson_id, item in lessons.items():
        reference = format_transcript(item.corrected or [])
        texts = {"initial": format_transcript(item.initial or []), **raw.get(lesson_id, {})}
        for row, text in texts.items():
            details = module.compute(text, reference=reference, options=options).details
            stats[row][lesson_id] = (details[num_key], details[den_key])

    def rate(row: str, lesson_id: Optional[str]) -> Optional[float]:
        if lesson_id is None:  # all lessons, only when the row has every lesson
            if len(stats.get(row, {})) < len(lessons):
                return None
            numerator, denominator = map(sum, zip(*stats[row].values()))
        elif lesson_id in stats.get(row, {}):
            numerator, denominator = stats[row][lesson_id]
        else:
            return None
        return numerator / denominator if denominator else None

    keys: list[Optional[str]] = [*lessons, None]
    best = {}
    for key in keys:
        values = [v for v in (rate(c, key) for c in columns) if v is not None]
        best[key] = (max if higher_is_better else min)(values) if values else None
    rows = []
    for row in ["initial", *columns]:
        cells = []
        for key in keys:
            value = rate(row, key)
            text = "–" if value is None else f"{value * 100:.2f}%"
            if value is not None and row != "initial" and value == best[key]:
                text = f"<strong>{text}</strong>"
            cells.append(f"<td>{text}</td>")
        rows.append(f"<tr><td class='label'>{html.escape(row)}</td>{''.join(cells)}</tr>")
    head = "".join(f"<th><a href=\"#{html.escape(l)}\">{html.escape(l)}</a></th>" for l in lessons)
    return f"""
<table class="summary">
  <thead><tr><th>{html.escape(title)} {'↑' if higher_is_better else '↓'}</th>{head}<th>all</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>"""


def write_correction_errors(path: Path, *, config: dict, step_name: str, jobs: list[Any], db: BenchDB,
                            case_sensitive: bool = True) -> Path:
    compare = Comparator(case_sensitive)
    columns, outputs, raw = _model_outputs(jobs, db)
    lessons = {}
    for job in jobs:
        lessons.setdefault(job.item.id, job.item)

    # {column: {lesson: {severity: wrong segments}}}
    wrong_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    sections = []
    for lesson_id, item in lessons.items():
        initial = {(s.start, s.end): s.text for s in item.initial or []}
        lesson_outputs = outputs.get(lesson_id, {})
        rows = []
        for gold in item.corrected or []:
            key = (gold.start, gold.end)
            init_text = initial.get(key, "")
            init_severity = compare.severity(init_text, gold.text)
            cells, any_wrong = [], False
            for column in columns:
                if column not in lesson_outputs:
                    cells.append("<td class='na'></td>")
                    continue
                text = lesson_outputs[column].get(key)
                if text is None:
                    severity = "fold"
                    cells.append("<td class='wrong fold'><em>missing segment</em></td>")
                else:
                    severity = compare.severity(text, gold.text)
                    if severity is None:
                        cells.append("<td></td>")
                        continue
                    cells.append(f"<td class='wrong {severity}'>{compare.highlight(text, gold.text)}</td>")
                wrong_counts[column][lesson_id][severity] += 1
                any_wrong = True
            if init_severity:
                wrong_counts["initial"][lesson_id][init_severity] += 1
            if not (init_severity or any_wrong):
                continue
            if init_severity:
                init_cell = f"<td class='wrong {init_severity}'>{compare.highlight(init_text, gold.text)}</td>"
            else:
                init_cell = f"<td>{html.escape(init_text)}</td>"
            rows.append(
                f"<tr><td class='ts'>{_format_seconds(gold.start)} – {_format_seconds(gold.end)}</td>"
                f"{init_cell}<td class='gold'>{html.escape(gold.text)}</td>{''.join(cells)}</tr>"
            )

        missing = [c for c in columns if c not in lesson_outputs]
        note = f"<p class='meta'>No output for: {html.escape(', '.join(missing))}</p>" if missing else ""
        head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
        sections.append(f"""
<section class="lesson" id="{html.escape(lesson_id)}">
<h2>{html.escape(lesson_id)}</h2>{note}
<table>
  <thead><tr><th>time</th><th>initial</th><th>corrected</th>{head}</tr></thead>
  <tbody>{''.join(rows) or f"<tr><td colspan='{3 + len(columns)}'>No error.</td></tr>"}</tbody>
</table>
</section>""")

    def count_cell(by_severity: dict[str, int], strong: bool = False) -> str:
        total = sum(by_severity.values())
        split = "".join(f"<span class='n {s}' title='{s}'>{by_severity.get(s, 0)}</span>"
                        for s in reversed(SEVERITIES))
        return f"<td>{f'<strong>{total}</strong>' if strong else total}{split}</td>"

    summary_rows = []
    for column in ["initial", *columns]:
        counts = wrong_counts.get(column, {})
        available = [l for l in lessons if column == "initial" or column in outputs.get(l, {})]
        cells = "".join(
            count_cell(counts.get(lesson_id, {})) if lesson_id in available else "<td>–</td>" for lesson_id in lessons
        )
        totals_by_severity: dict[str, int] = defaultdict(int)
        for by_severity in counts.values():
            for severity, n in by_severity.items():
                totals_by_severity[severity] += n
        total = count_cell(totals_by_severity, strong=True) if available else "<td>–</td>"
        summary_rows.append(f"<tr><td class='label'>{html.escape(column)}</td>{cells}{total}</tr>")
    totals = "".join(f"<td>{len(item.corrected or [])}</td>" for item in lessons.values())
    step_options = dict(metric_specs((config.get("steps") or {}).get(step_name) or {}))
    metric_tables = "".join(
        _metric_table(title, metric, keys, higher, step_options.get(metric, {}), lessons, columns, raw)
        for title, metric, keys, higher in METRIC_TABLES
    )
    summary = f"""
<table class="summary">
  <thead><tr><th>segments different from corrected</th>{''.join(f'<th><a href="#{html.escape(l)}">{html.escape(l)}</a></th>' for l in lessons)}<th>total</th></tr></thead>
  <tbody>{''.join(summary_rows)}<tr class='muted'><td class='label'>segments</td>{totals}<td></td></tr></tbody>
</table>{metric_tables}"""

    options = "".join(f"<option value='{html.escape(l)}'>{html.escape(l)}</option>" for l in lessons)
    picker = f"""
<p class="picker"><label for="lesson">Lesson </label><select id="lesson">{options}</select></p>"""

    name = (config.get("campaign") or {}).get("name", "campaign")
    rule = "punctuation and spacing ignored, case counts" if case_sensitive else "punctuation, spacing and case ignored"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Correction errors – {html.escape(name)}</title>
<style>
  :root {{ color-scheme: light dark; background: Canvas; color: CanvasText; }}
  body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
  .meta {{ opacity: .7; font-size: .9rem; margin: .1rem 0; }}
  table {{ border-collapse: collapse; margin: .5rem 0 1.5rem; font-size: .85rem; }}
  th, td {{ border: 1px solid rgba(128, 128, 128, .35); padding: .3rem .5rem; vertical-align: top; text-align: left; }}
  th {{ background: rgba(128, 128, 128, .15); position: sticky; top: 0; }}
  td {{ max-width: 22rem; }}
  td.ts {{ white-space: nowrap; opacity: .7; }}
  td.gold {{ background: rgba(76, 175, 80, .12); }}
  td.wrong.fold {{ background: rgba(229, 57, 53, .2); }}
  td.wrong.norm {{ background: rgba(251, 140, 0, .18); }}
  td.wrong.minor {{ background: rgba(253, 216, 53, .16); }}
  td.na {{ background: rgba(128, 128, 128, .12); }}
  mark {{ color: inherit; border-radius: 2px; padding: 0 1px; }}
  mark.fold, .n.fold {{ background: rgba(229, 57, 53, .5); }}
  mark.norm, .n.norm {{ background: rgba(251, 140, 0, .5); }}
  mark.minor, .n.minor {{ background: rgba(253, 216, 53, .5); }}
  mark.gap {{ font-weight: bold; padding: 0 2px; user-select: none; }}
  .n {{ display: inline-block; min-width: 1.4em; margin-left: .3rem; padding: 0 .2rem; border-radius: 3px;
        font-size: .75rem; text-align: center; }}
  .legend mark {{ padding: 0 .3rem; }}
  table.summary td {{ text-align: right; }}
  table.summary td.label {{ text-align: left; }}
  tr.muted td {{ opacity: .6; }}
  a {{ color: LinkText; }}
  .picker {{ margin: 1rem 0 0; }}
  .picker select {{ font: inherit; padding: .2rem .4rem; }}
  .picker:not(.ready) {{ display: none; }}
  .picker.ready ~ section.lesson:not(.shown) {{ display: none; }}
</style></head><body>
<h1>Correction errors – {html.escape(step_name)}</h1>
<p class="meta">{html.escape(name)} – dataset {html.escape(str(config.get('dataset_version', '?')))}
 – generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p class="meta">A segment is wrong when its words differ from corrected.md ({rule}). Rows: segments
where the initial transcript or a model is wrong. Model cells: empty = matches corrected.md,
colored = different (differing words highlighted, ‸ = missing words), grey = no output. First successful
repeat of each model.</p>
<p class="meta legend">Severity (the cell takes its most important one; summary: segments, then per severity):
<mark class="fold">real error</mark> still counted by wer_fold –
<mark class="norm">transliteration variant</mark> counted by wer_norm, not by wer_fold (Parashah / parasha) –
<mark class="minor">minor</mark> case, accents, apostrophes or hyphens only (Sinaï / Sinai, ha-Nahar / HaNahar).</p>
{summary}
{picker}
{''.join(sections)}
<script>
  const select = document.getElementById("lesson");
  const show = id => {{
    document.querySelectorAll("section.lesson").forEach(s => s.classList.toggle("shown", s.id === id));
  }};
  const fromHash = () => {{
    const id = decodeURIComponent(location.hash.slice(1));
    if ([...select.options].some(o => o.value === id)) select.value = id;
    show(select.value);
  }};
  select.addEventListener("change", () => {{ history.replaceState(null, "", "#" + encodeURIComponent(select.value)); show(select.value); }});
  window.addEventListener("hashchange", fromHash);
  fromHash();
  select.parentElement.classList.add("ready");
</script>
</body></html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
