"""Character error rate between the output and the gold transcript.

Same as wer, on the characters of the normalized text (words joined by single spaces), so a word
wrongly split or merged costs one character instead of two words.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.wer import error_rate

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    return error_rate(output, reference, chars=True, options=options)
