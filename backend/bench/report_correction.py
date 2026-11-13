"""HTML report of the correction errors, segment by segment.

One table per lesson: a row per segment where the initial transcript or at least one model differs
from corrected.md; columns: timestamps, initial, corrected, then one column per model x prompt
(first successful repeat). A model cell is empty when the model's segment matches corrected.md,
and shows the model text on a red background otherwise (differing words highlighted).
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rapidfuzz.distance import Levenshtein

from bench.dataset import _format_seconds, parse_transcript
from bench.db import BenchDB
from bench.metrics.text import strip_speaker_tag, tokenize


class Comparator:
    """Compares texts with corrected.md, ignoring punctuation and spacing (case counts by default)."""

    def __init__(self, case_sensitive: bool = True):
        self.lowercase = not case_sensitive

    def words(self, text: str) -> list[str]:
        return tokenize(strip_speaker_tag(text), lowercase=self.lowercase)

    def same(self, text: str, gold: str) -> bool:
        return self.words(text) == self.words(gold)

    def highlight(self, text: str, gold: str) -> str:
        """HTML of `text` with the words that differ from `gold` in <mark>."""
        raw = text.split()
        units = [(i, " ".join(self.words(w))) for i, w in enumerate(raw)]
        units = [(i, u) for i, u in units if u]  # punctuation-only words are never marked
        marked: set[int] = set()
        for op in Levenshtein.opcodes([u for _, u in units], self.words(gold)):
            if op.tag in ("replace", "delete"):
                marked.update(units[k][0] for k in range(op.src_start, op.src_end))
        return " ".join(f"<mark>{html.escape(w)}</mark>" if i in marked else html.escape(w) for i, w in enumerate(raw))


def _model_outputs(jobs: list[Any], db: BenchDB) -> tuple[list[str], dict[str, dict[str, dict]]]:
    """Columns (model / prompt labels) and {lesson: {column: {(start, end): text}}} (first OK repeat)."""
    several_prompts = len({j.prompt_name for j in jobs}) > 1
    columns: list[str] = []
    outputs: dict[str, dict[str, dict]] = defaultdict(dict)
    for job in sorted(jobs, key=lambda j: j.repeat):
        column = f"{job.model_alias} / {job.prompt_name}" if several_prompts else job.model_alias
        if column not in columns:
            columns.append(column)
        if job.cached_id is None or column in outputs[job.item.id]:
            continue
        segments, _ = parse_transcript(db.generation(job.cached_id)["output"] or "")
        outputs[job.item.id][column] = {(s.start, s.end): s.text for s in segments}
    return columns, outputs


def write_correction_errors(path: Path, *, config: dict, step_name: str, jobs: list[Any], db: BenchDB,
                            case_sensitive: bool = True) -> Path:
    compare = Comparator(case_sensitive)
    columns, outputs = _model_outputs(jobs, db)
    lessons = {}
    for job in jobs:
        lessons.setdefault(job.item.id, job.item)

    wrong_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sections = []
    for lesson_id, item in lessons.items():
        initial = {(s.start, s.end): s.text for s in item.initial or []}
        lesson_outputs = outputs.get(lesson_id, {})
        rows = []
        for gold in item.corrected or []:
            key = (gold.start, gold.end)
            init_text = initial.get(key, "")
            init_wrong = not compare.same(init_text, gold.text)
            cells, any_wrong = [], False
            for column in columns:
                if column not in lesson_outputs:
                    cells.append("<td class='na'></td>")
                    continue
                text = lesson_outputs[column].get(key)
                if text is None:
                    cells.append("<td class='wrong'><em>missing segment</em></td>")
                elif compare.same(text, gold.text):
                    cells.append("<td></td>")
                    continue
                else:
                    cells.append(f"<td class='wrong'>{compare.highlight(text, gold.text)}</td>")
                wrong_counts[column][lesson_id] += 1
                any_wrong = True
            if init_wrong:
                wrong_counts["initial"][lesson_id] += 1
            if not (init_wrong or any_wrong):
                continue
            init_cell = compare.highlight(init_text, gold.text) if init_wrong else html.escape(init_text)
            rows.append(
                f"<tr><td class='ts'>{_format_seconds(gold.start)} – {_format_seconds(gold.end)}</td>"
                f"<td>{init_cell}</td><td class='gold'>{html.escape(gold.text)}</td>{''.join(cells)}</tr>"
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

    summary_rows = []
    for column in ["initial", *columns]:
        counts = wrong_counts.get(column, {})
        available = [l for l in lessons if column == "initial" or column in outputs.get(l, {})]
        cells = "".join(
            f"<td>{counts.get(lesson_id, 0) if lesson_id in available else '–'}</td>" for lesson_id in lessons
        )
        total = sum(counts.values()) if available else "–"
        summary_rows.append(f"<tr><td class='label'>{html.escape(column)}</td>{cells}"
                            f"<td><strong>{total}</strong></td></tr>")
    totals = "".join(f"<td>{len(item.corrected or [])}</td>" for item in lessons.values())
    summary = f"""
<table class="summary">
  <thead><tr><th>segments different from corrected</th>{''.join(f'<th><a href="#{html.escape(l)}">{html.escape(l)}</a></th>' for l in lessons)}<th>total</th></tr></thead>
  <tbody>{''.join(summary_rows)}<tr class='muted'><td class='label'>segments</td>{totals}<td></td></tr></tbody>
</table>"""

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
  td.wrong {{ background: rgba(229, 57, 53, .22); }}
  td.na {{ background: rgba(128, 128, 128, .12); }}
  mark {{ background: rgba(229, 57, 53, .45); color: inherit; border-radius: 2px; padding: 0 1px; }}
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
red = different (differing words highlighted), grey = no output. First successful repeat of each model.</p>
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
