"""length_words: number of words of the output versus a target.

Options: `target` (required), `tolerance` (relative, default 0.2: in range when the number of
words is within target ± 20 %). Words are counted as in length_ratio.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.text import count_words

HIGHER_IS_BETTER = None  # neither: the target is a range
REPORT_DETAILS = {"in_range": True, "abs_deviation": False}
PERCENT = False
PERCENT_DETAILS = {"in_range", "abs_deviation"}
DIGITS = 0
NEEDS_REFERENCE = False

DEFAULT_TOLERANCE = 0.2


def check_options(options: dict) -> list[str]:
    problems = []
    target = options.get("target")
    if not isinstance(target, (int, float)) or target <= 0:
        problems.append(f"'target' (number of words) is required and must be positive, got {target!r}")
    tolerance = options.get("tolerance", DEFAULT_TOLERANCE)
    if not isinstance(tolerance, (int, float)) or tolerance < 0:
        problems.append(f"'tolerance' must be a positive fraction (e.g. 0.2), got {tolerance!r}")
    return problems


def compute(output: str, *, input_text: Optional[str] = None, reference: Optional[str] = None,
            options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    target = float(options["target"])
    tolerance = float(options.get("tolerance", DEFAULT_TOLERANCE))
    words = count_words(output)
    deviation = (words - target) / target
    return MetricResult(float(words), {
        "target": target,
        "tolerance": tolerance,
        "deviation": deviation,
        "abs_deviation": abs(deviation),
        "in_range": float(abs(deviation) <= tolerance + 1e-12),
    })
