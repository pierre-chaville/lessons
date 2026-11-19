"""Metric columns of a step and their aggregation over lessons and repeats (review app tables)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Callable, Optional

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


def columns(step: dict) -> list[tuple[str, dict, Column]]:
    """(metric, options, column) for the implemented metrics of a step, details columns included."""
    result = []
    for name, options in metric_specs(step):
        try:
            module = get_metric_module(name)
        except KeyError:
            continue
        percent = getattr(module, "PERCENT", False)
        percent_details = getattr(module, "PERCENT_DETAILS", set(module.REPORT_DETAILS) if percent else set())
        digits = getattr(module, "DIGITS", 3)
        result.append((name, options, Column(name, module.HIGHER_IS_BETTER, lambda v, d: v, percent, digits)))
        for key, higher in module.REPORT_DETAILS.items():
            result.append((name, options, Column(
                key, higher, lambda v, d, key=key: d.get(key), key in percent_details, digits
            )))
    return result


def aggregate(values_by_lesson: dict[str, list[float]]) -> tuple[Optional[float], Optional[float]]:
    """Mean over lessons of the mean over repeats, and mean spread (std) between repeats."""
    lesson_means = [mean(v) for v in values_by_lesson.values() if v]
    spreads = [pstdev(v) for v in values_by_lesson.values() if len(v) >= 2]
    return (mean(lesson_means) if lesson_means else None), (mean(spreads) if spreads else None)


def baseline_row(jobs: list[Any], step_columns) -> Optional[tuple[str, list[tuple[Optional[float], Optional[float]]]]]:
    """(label, cells) of the row scoring a non-model text with the same metrics:
    - correction: the input itself, i.e. what the model has to improve on;
    - edition / summary: the hand-made reference (edited.md / summary.md), i.e. the expected level.
    Judge metrics are not computed (it would cost calls)."""
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
    for metric, options, column in step_columns:
        by_lesson: dict[str, list[float]] = defaultdict(list)
        if getattr(get_metric_module(metric), "JUDGE", False):
            cells.append((None, None))
            continue
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
        cells.append(aggregate(by_lesson))
    return label, cells
