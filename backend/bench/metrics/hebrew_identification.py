"""hebrew_identification (level A): share of the Hebrew words of corrected.md that the model
recognized. Replaces hebrew_term_accuracy for the transcripts corrected in Hebrew script.

Each Hebrew word of the gold is aligned, segment by segment, with its counterpart in the output
and gets a category (metrics/hebrew.py):

- exact: same word without points (פֶּסַח = פֶּסַח)
- spelling_variant: same glossary entry, or same skeleton when not both in the glossary (מִצְוֹת / מִצְווֹת)
- unvocalized: right word, but without vowel points (the transliteration needs them)
- form_variant: same stem, another ending (singular / plural: שִׁיעוּר / שִׁיעוּרִים): not identified
- prefix_variant: same word with a different prefix (עֹמֶר / הָעֹמֶר)
- latin_correct: written in Latin script, a right transliteration (Pessaḥ): glossary transliteration
  or same consonants
- latin_uncorrected: Latin word left as in the raw transcript (Amalek, Amara)
- wrong_word: another word
- missing: no counterpart

Value = (exact + spelling_variant + prefix_variant + latin_correct) / gold Hebrew words, None when
the gold has no Hebrew word.

Options: glossary (default true): use the glossary of the app DB (its size is stored in the details).
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.hebrew import CATEGORIES, IDENTIFIED, analyze, check_glossary_option, he_key

HIGHER_IS_BETTER = True
PERCENT = True
REPORT_DETAILS = {"wrong_word": False, "missing": False, "latin_uncorrected": False}
PERCENT_DETAILS: set[str] = set()
TOP_ERRORS = 30


def check_options(options: dict) -> list[str]:
    return check_glossary_option(options)


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    analysis = analyze(output, reference, input_text or "", bool(options.get("glossary", True)))
    terms = analysis.terms
    counts = Counter(t.category for t in terms)
    errors = Counter(f"{t.gold} → {t.output or '∅'} [{t.category}]" for t in terms if t.category != "exact")
    identified = sum(counts[c] for c in IDENTIFIED)
    details = {
        "terms": len(terms),
        "distinct_terms": len({he_key(t.gold) for t in terms}),
        "identified": identified,
        **{c: counts[c] for c in CATEGORIES},
        "exact_niqqud": sum(t.niqqud_differs for t in terms),  # exact words with other vowel points
        "glossary_entries": analysis.glossary_entries,
        "segment_aligned": analysis.segment_aligned,
        "top_differences": [f"{e} (×{n})" if n > 1 else e for e, n in errors.most_common(TOP_ERRORS)],
    }
    return MetricResult(identified / len(terms) if terms else None, details)
