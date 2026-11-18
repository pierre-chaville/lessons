"""Bench metrics, one module per metric (see README "Metrics").

Every deterministic metric module exposes:

    def compute(output: str, *, input_text: str, reference: str | None, options: dict | None = None) -> MetricResult

- `output`: output of the step being scored
- `input_text`: input of the step (initial.md for correction, corrected.md for edition in gold mode)
- `reference`: gold text (corrected.md for correction, edited.md for edition, summary.md for summary)
- `options`: metric options from the campaign (e.g. `{strict: true}`)

Optional:
- `NEEDS_REFERENCE` (default True): False if the metric does not use `reference`
- `check_options(options) -> list[str]`: problems in the options, reported by `--check`

and, for the report:
- `HIGHER_IS_BETTER`: bool, or None when neither (e.g. a length checked against a range)
- `REPORT_DETAILS`: {detail key: higher_is_better} of the details shown next to the value
- `PERCENT`: True for ratios, displayed as percentages
- `PERCENT_DETAILS` (optional): detail keys displayed as percentages (default: all if PERCENT)
- `DIGITS` (optional, default 3): decimals of the value when not a percentage

Judge metrics (`JUDGE = True`, e.g. idea_coverage, faithfulness) are scored by bench/judge.py:
they take the dataset item and the judge (`compute(..., item=, judge=)`), expose `VERSION`
and `estimate_tokens(output, *, input_text, item, options)`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable, Optional

IMPLEMENTED = (
    "wer", "wer_norm", "wer_fold", "cer", "edit_precision_recall", "overcorrection_rate",
    "length_ratio", "length_words", "hebrew_quotes_preserved", "hebrew_term_accuracy",
    "idea_coverage", "faithfulness",
)


@dataclass
class MetricResult:
    value: Optional[float]  # None when undefined (e.g. empty reference)
    details: dict[str, Any] = field(default_factory=dict)


def get_metric_module(name: str) -> ModuleType:
    if name not in IMPLEMENTED:
        raise KeyError(f"unknown metric {name!r} (implemented: {', '.join(IMPLEMENTED)})")
    return importlib.import_module(f"bench.metrics.{name}")


def get_metric(name: str) -> Callable[..., MetricResult]:
    return get_metric_module(name).compute
