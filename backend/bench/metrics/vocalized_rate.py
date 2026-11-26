"""vocalized_rate (level A): share of the Hebrew-script words of the output (counterparts of a
vocalized Hebrew word of corrected.md) that have vowel points: the transliteration needs them.

Gold words without vowel points and abbreviations in the output (ה׳, חז״ל) are left out. None when
nothing is counted.

Options: glossary (default true), as hebrew_identification.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.hebrew import analyze, check_glossary_option, has_vowels, needs_vowels

HIGHER_IS_BETTER = True
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}
TOP_UNVOCALIZED = 20


def check_options(options: dict) -> list[str]:
    return check_glossary_option(options)


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    analysis = analyze(output, reference, input_text or "", bool(options.get("glossary", True)))
    counted = [t for t in analysis.terms if t.output_hebrew and has_vowels(t.gold) and needs_vowels(t.output)]
    vocalized = sum(has_vowels(t.output) for t in counted)
    bare = Counter(f"{t.gold} → {t.output}" for t in counted if not has_vowels(t.output))
    details = {
        "counted": len(counted),
        "vocalized": vocalized,
        "unvocalized": len(counted) - vocalized,
        "top_unvocalized": [f"{e} (×{n})" if n > 1 else e for e, n in bare.most_common(TOP_UNVOCALIZED)],
    }
    return MetricResult(vocalized / len(counted) if counted else None, details)
