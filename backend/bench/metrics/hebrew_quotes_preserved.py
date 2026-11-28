"""hebrew_quotes_preserved: share of the Hebrew of the input found in the output.

Two kinds of expected items, each counted once per distinct item:
- Hebrew-script spans of the input (runs of Hebrew words, at least 2 letters). Vowel points and
  cantillation are ignored; a span is found when its fuzzy match (rapidfuzz partial_ratio) against
  the Hebrew of the output reaches `threshold` (default 85).
- Transliterated terms: entries of the app glossary (`glossary: true`, default) and the extra
  `terms:` of the options, present in the input. A term is found when the output contains one of
  its spellings (the glossary standard form or a variation), compared on normalized words where
  hyphens and apostrophes are ignored (`Beit ha-Miqdash` contains `HaMiqdash`).

Value = found / expected; None when the input has neither Hebrew script nor known terms.
The glossary is read from the app DB at scoring time: its size is stored in the details.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Optional

from rapidfuzz import fuzz

from bench.metrics import MetricResult
from bench.metrics.text import contains_words, plain_text, tokenize

HIGHER_IS_BETTER = True
REPORT_DETAILS: dict[str, bool] = {}
PERCENT = True
NEEDS_REFERENCE = False

DEFAULT_THRESHOLD = 85
_LETTERS = "\u05d0-\u05ea\ufb1d-\ufb4f"
_MARKS = "\u0591-\u05c7"
_HEBREW_SPAN_RE = re.compile(
    rf"[{_LETTERS}][{_LETTERS}{_MARKS}\"'\u05f3\u05f4]*"
    rf"(?:[\s\u05be-]+[{_LETTERS}][{_LETTERS}{_MARKS}\"'\u05f3\u05f4]*)*"
)
_MARKS_RE = re.compile(rf"[{_MARKS}\u05f3\u05f4\"']")


def check_options(options: dict) -> list[str]:
    problems = []
    threshold = options.get("threshold", DEFAULT_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
        problems.append(f"'threshold' must be between 0 and 100, got {threshold!r}")
    terms = options.get("terms", [])
    if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
        problems.append("'terms' must be a list of strings")
    return problems


def hebrew_spans(text: str) -> list[str]:
    """Distinct Hebrew-script spans, without vowel points, in order of appearance."""
    spans: list[str] = []
    for match in _HEBREW_SPAN_RE.finditer(unicodedata.normalize("NFC", text)):
        span = " ".join(_MARKS_RE.sub("", match.group()).replace("\u05be", " ").replace("-", " ").split())
        if len(span.replace(" ", "")) >= 2 and span not in spans:
            spans.append(span)
    return spans


@lru_cache(maxsize=1)
def _app_glossary() -> tuple[tuple[str, tuple[str, ...], bool], ...]:
    from bench.steps import _load_glossary_rules

    return tuple((r.standard, tuple(r.variations), r.exact_case) for r in _load_glossary_rules())


def _terms(options: dict) -> list[tuple[str, tuple[str, ...], bool]]:
    """(standard form, spellings, exact case) of the transliterated terms to look for."""
    terms = list(_app_glossary()) if options.get("glossary", True) else []
    terms += [(t, (t,), False) for t in options.get("terms", [])]
    return terms


def _words(text: str, lowercase: bool = True) -> list[str]:
    """Words for term matching: hyphens and apostrophes ignored (`ha-Miqdash` = `HaMiqdash`)."""
    return [w for w in (t.replace("-", "").replace("'", "") for t in tokenize(text, lowercase=lowercase)) if w]


def _has_term(words: dict[bool, list[str]], spellings: tuple[str, ...], exact_case: bool) -> bool:
    return any(contains_words(words[exact_case], _words(s, lowercase=not exact_case)) for s in spellings)


def compute(output: str, *, input_text: str, reference: Optional[str] = None,
            options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    threshold = float(options.get("threshold", DEFAULT_THRESHOLD))
    source, result = plain_text(input_text), plain_text(output)

    expected_spans = hebrew_spans(source)
    output_hebrew = " ".join(hebrew_spans(result))
    missing_spans = [
        s for s in expected_spans if not output_hebrew or fuzz.partial_ratio(s, output_hebrew) < threshold
    ]

    terms = _terms(options)
    source_words = {False: _words(source), True: _words(source, lowercase=False)}
    output_words = {False: _words(result), True: _words(result, lowercase=False)}
    expected_terms = {
        standard: (spellings, exact) for standard, spellings, exact in terms
        if _has_term(source_words, spellings, exact)
    }
    missing_terms = [t for t, (spellings, exact) in expected_terms.items() if not _has_term(output_words, spellings, exact)]

    expected = len(expected_spans) + len(expected_terms)
    found = expected - len(missing_spans) - len(missing_terms)
    details = {
        "hebrew_spans": len(expected_spans),
        "hebrew_spans_found": len(expected_spans) - len(missing_spans),
        "terms": len(expected_terms),
        "terms_found": len(expected_terms) - len(missing_terms),
        "missing_hebrew": missing_spans[:30],
        "missing_terms": missing_terms[:30],
        "glossary_entries": len(terms) - len(options.get("terms", [])),
        "threshold": threshold,
    }
    return MetricResult(found / expected if expected else None, details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the Hebrew items of the input (spans and known terms) found in the output'
