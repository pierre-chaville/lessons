"""hebrew_script_rate (level A): share of the Hebrew words of corrected.md that the output writes in
Hebrew script, i.e. compliance with the instruction of the correction prompt (whatever the word).

Counted over the gold Hebrew words that have a counterpart in the output (see
hebrew_identification; missing words are left out). None when there is none.

Options: glossary (default true), as hebrew_identification.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.hebrew import analyze, check_glossary_option

HIGHER_IS_BETTER = True
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}
TOP_LATIN = 20


def check_options(options: dict) -> list[str]:
    return check_glossary_option(options)


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    analysis = analyze(output, reference, input_text or "", bool(options.get("glossary", True)))
    present = [t for t in analysis.terms if t.output is not None]
    hebrew = sum(t.output_hebrew for t in present)
    latin = Counter(f"{t.gold} → {t.output}" for t in present if not t.output_hebrew)
    details = {
        "counted": len(present),
        "hebrew_script": hebrew,
        "latin_script": len(present) - hebrew,
        "top_latin": [f"{e} (×{n})" if n > 1 else e for e, n in latin.most_common(TOP_LATIN)],
    }
    return MetricResult(hebrew / len(present) if present else None, details)
