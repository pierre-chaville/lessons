"""wer_french (level B): word error rate of the French text alone.

In the gold and in the output, each Hebrew passage becomes one `⟨HE⟩` token, and so does each
Latin word of the output standing for a gold Hebrew word (Torah for תּוֹרָה, see
hebrew_identification): the Hebrew words are scored by level A, this level isolates the French
correction (agreements, wording). Accents count, case does not by default; punctuation
does not; numbers in digits equal numbers in words (2 = deux). Computed segment by segment when the
output keeps the segments of corrected.md.

Value = (substitutions + deletions + insertions) / words of the gold (⟨HE⟩ tokens included).
Details: `large_edits` counts the insertions and replacements of more than 3 words (rewritten
passages: `drift` in the review app), listed in `large_edit_examples`; `french_errors` counts the
other differences (`french_error`, a Hebrew passage missing from the output excepted: level A
reports it as missing; it still counts in the value), listed in `top_errors`; `french_variants` counts the words
that differ by one letter (a harmless variant, not an error: option one_letter_variants, default
true; it also hides one-letter agreements such as reçues / reçus); `minor` counts the words equal
for the metric but written differently (2 / deux, case). The review app segment view counts the same items.

Options: one_letter_variants (default true), case_sensitive (default false: French words compared in lowercase, a case difference is `minor`), glossary (default true, used to align the Hebrew words).
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from bench.dataset import _format_seconds
from bench.metrics import MetricResult
from bench.metrics.hebrew import analyze, check_glossary_option
from bench.metrics.text import ErrorCounts

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS = {"french_errors": False, "large_edits": False}
PERCENT_DETAILS: set[str] = set()
TOP_ERRORS = 30
MAX_LARGE_EXAMPLES = 15


def check_options(options: dict) -> list[str]:
    problems = check_glossary_option(options)
    for name in ("case_sensitive", "one_letter_variants"):
        if not isinstance(options.get(name, False), bool):
            problems.append(f"'{name}' must be true or false")
    return problems


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    case_sensitive = bool(options.get("case_sensitive", False))
    analysis = analyze(output, reference, input_text or "", bool(options.get("glossary", True)), case_sensitive,
                       bool(options.get("one_letter_variants", True)))
    total = ErrorCounts()
    errors: Counter[str] = Counter()
    large = []
    for unit in analysis.units:
        total += unit.french_counts
        for edit in unit.edits:
            if edit.category == "drift":
                large.append(f"[{_format_seconds(unit.start)}] {edit.label}" if unit.start is not None else edit.label)
            else:
                errors[edit.label] += 1
    details = {
        "errors": total.errors,
        "substitutions": total.substitutions,
        "deletions": total.deletions,
        "insertions": total.insertions,
        "ref_length": total.ref_length,
        "output_length": total.hyp_length,
        "french_errors": sum(errors.values()),
        "large_edits": len(large),
        "french_variants": sum(len(u.french_variants) for u in analysis.units),
        "minor": sum(len(u.minor) for u in analysis.units),
        "large_edit_examples": large[:MAX_LARGE_EXAMPLES],
        "segment_aligned": analysis.segment_aligned,
        "top_errors": [f"{e} (×{n})" if n > 1 else e for e, n in errors.most_common(TOP_ERRORS)],
    }
    return MetricResult(total.rate(), details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the words of the gold, Hebrew passages counted as one ⟨HE⟩ token (errors / gold words)'
DETAIL_DOCS = {
    'french_errors': 'French differences of 3 words or less (agreements, wording): red `French error` in the segment view. Unit: number of differences.',
    'large_edits': 'Insertions / replacements of more than 3 words (rewritten passages): purple `content drift`. Unit: number of edits.',
}
