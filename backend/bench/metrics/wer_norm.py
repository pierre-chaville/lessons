"""WER on normalized words: as wer (lowercase, punctuation removed), and also without accents,
Hebrew vowel points, inner apostrophes and hyphens (`Sinaï` = `Sinai`, `ha-Nahar` = `HaNahar`).

Compared with wer, shows how many errors are only accents or word punctuation.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.wer import error_rate

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    return error_rate(output, reference, chars=False, options=options, level="norm")
