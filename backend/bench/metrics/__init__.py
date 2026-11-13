"""Bench metrics, one module per metric (see README "Metrics").

Every deterministic metric module exposes:

    def compute(output: str, *, input_text: str, reference: str, options: dict | None = None) -> MetricResult

- `output`: output of the step being scored
- `input_text`: input of the step (initial.md for correction)
- `reference`: gold text (corrected.md for correction)
- `options`: metric options from the campaign (e.g. `{strict: true}`)

and, for the report:
- `HIGHER_IS_BETTER`: bool
- `REPORT_DETAILS`: {detail key: higher_is_better} of the details shown next to the value
- `PERCENT`: True for ratios, displayed as percentages
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable, Optional

IMPLEMENTED = ("wer", "cer", "edit_precision_recall", "overcorrection_rate")


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
