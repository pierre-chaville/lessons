"""length_ratio: words of the output / words of the input, checked against a [min, max] range.

Options: `min`, `max` (both optional). Words are counted on the text only: timestamps, speaker
tags, markdown symbols and punctuation are not words.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.text import count_words

HIGHER_IS_BETTER = None  # neither: the target is a range
REPORT_DETAILS = {"in_range": True}
PERCENT = False
PERCENT_DETAILS = {"in_range"}
NEEDS_REFERENCE = False


def check_options(options: dict) -> list[str]:
    problems = []
    for key in ("min", "max"):
        value = options.get(key)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            problems.append(f"'{key}' must be a positive number, got {value!r}")
    low, high = options.get("min"), options.get("max")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low > high:
        problems.append(f"'min' ({low}) is greater than 'max' ({high})")
    return problems


def compute(output: str, *, input_text: str, reference: Optional[str] = None,
            options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    low, high = options.get("min"), options.get("max")
    words_output, words_input = count_words(output), count_words(input_text)
    details = {"words_output": words_output, "words_input": words_input, "min": low, "max": high}
    if not words_input:
        return MetricResult(None, details)
    ratio = words_output / words_input
    if low is not None or high is not None:
        details["in_range"] = float((low is None or ratio >= low) and (high is None or ratio <= high))
    return MetricResult(ratio, details)
