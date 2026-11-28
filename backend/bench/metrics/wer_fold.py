"""WER on folded words: wer_norm, then `text.fold` on each word, so that the spelling variants of
transliterated Hebrew are equal (`Parashah` = `parasha`, `passouq` = `pasuk`, `Shabbath` = `shabat`).

Compared with wer_norm, shows how many errors are only transliteration variants.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.wer import error_rate

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    return error_rate(output, reference, chars=False, options=options, level="fold")


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the words of the gold (errors / gold words)'
