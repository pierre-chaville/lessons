"""hebrew_term_accuracy: share of the Hebrew terms of corrected.md that the output spells right,
transliteration variants allowed (words compared with text.fold, as wer_fold).

Hebrew terms: words of the reference unknown to the French dictionary of pyspellchecker (Hebrew
script included). A French elision is removed before the lookup (`d'emounah` -> `emounah`) and
compound words are split on hyphens: the word is a term if one of its parts is unknown
(`ou-neqevah` is a term, `moment-là` is not). Words with digits, roman numerals, `etc`, `ok`
and words shorter than `min_length` (default 2) are ignored; `exclude:` lists extra words to
treat as French (inflected forms or names missing from the dictionary, e.g. `fructifiez`).

The folded words of the reference and of the output are aligned (Levenshtein); a term occurrence
is right when it is aligned with an identical folded word. Value = right / term occurrences, None
when the reference has no term. Details: the most frequent errors (`reference -> output`).
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Optional

from rapidfuzz.distance import Levenshtein

from bench.metrics import MetricResult
from bench.metrics.text import fold_word, plain_text, tokenize

HIGHER_IS_BETTER = True
REPORT_DETAILS: dict[str, bool] = {}
PERCENT = True

DEFAULT_MIN_LENGTH = 2
TOP_ERRORS = 20
_ELISION_RE = re.compile(r"^(?:c|d|j|l|m|n|s|t|qu|jusqu|lorsqu|puisqu|quoiqu|presqu)'(?=.)")
_NOT_TERMS_RE = re.compile(r"^(?:[ivx]+|etc|ok)$")  # roman numerals and words missing from the dictionary


def check_options(options: dict) -> list[str]:
    problems = []
    min_length = options.get("min_length", DEFAULT_MIN_LENGTH)
    if not isinstance(min_length, int) or min_length < 1:
        problems.append(f"'min_length' must be a positive integer, got {min_length!r}")
    exclude = options.get("exclude", [])
    if not isinstance(exclude, list) or not all(isinstance(w, str) for w in exclude):
        problems.append("'exclude' must be a list of strings")
    return problems


@lru_cache(maxsize=1)
def _french_words() -> frozenset[str]:
    from spellchecker import SpellChecker

    return frozenset(SpellChecker(language="fr", distance=1).word_frequency.dictionary)


def is_hebrew_term(token: str, exclude: frozenset[str] = frozenset(), min_length: int = DEFAULT_MIN_LENGTH) -> bool:
    """`token`: a word of `tokenize` (lowercase, inner apostrophes and hyphens kept)."""
    if len(token) < min_length or any(c.isdigit() for c in token) or token in exclude or _NOT_TERMS_RE.match(token):
        return False
    french = _french_words()
    if token in french:
        return False
    parts = [_ELISION_RE.sub("", p).strip("'") for p in token.split("-")]
    return any(p and p not in french and p not in exclude for p in parts)


def compute(output: str, *, input_text: str = "", reference: str,
            options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    exclude = frozenset(w.lower() for w in options.get("exclude", []))
    min_length = int(options.get("min_length", DEFAULT_MIN_LENGTH))

    ref_tokens = tokenize(plain_text(reference))
    ref = [(fold_word(t), is_hebrew_term(t, exclude, min_length), t) for t in ref_tokens]
    ref = [r for r in ref if r[0]]
    out_tokens = [t for t in tokenize(plain_text(output)) if fold_word(t)]
    out = [fold_word(t) for t in out_tokens]

    right: set[int] = set()
    errors: Counter[str] = Counter()
    for op in Levenshtein.opcodes([r[0] for r in ref], out):
        if op.tag == "equal":
            right.update(range(op.src_start, op.src_end))
            continue
        same_length = op.src_end - op.src_start == op.dest_end - op.dest_start
        for k in range(op.src_start, op.src_end):
            if not ref[k][1]:
                continue
            if op.tag == "delete":
                got = "∅"
            elif same_length:
                got = out_tokens[op.dest_start + k - op.src_start]
            else:
                got = " ".join(out_tokens[op.dest_start:op.dest_end])
            errors[f"{ref[k][2]} -> {got}"] += 1

    terms = [k for k, r in enumerate(ref) if r[1]]
    n_right = sum(1 for k in terms if k in right)
    details = {
        "terms": len(terms),
        "distinct_terms": len({ref[k][0] for k in terms}),
        "right": n_right,
        "errors": len(terms) - n_right,
        "top_errors": [f"{e} (×{n})" if n > 1 else e for e, n in errors.most_common(TOP_ERRORS)],
    }
    return MetricResult(n_right / len(terms) if terms else None, details)
