"""Share of the words that were already correct but were modified by the model.

Already correct = initial words kept as is in the gold (initial -> gold diff). Modified = initial
words replaced or deleted in the output (initial -> output diff); words inserted by the model do
not modify an initial word and are not counted here (they lower edit precision).

value = correct words modified / correct words (None if no initial word is correct). Lower is better.
The diff is done segment by segment when the three transcripts keep the same segments.
Options: strict (default false): case and punctuation changes count.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.text import tokenize, unchanged_positions, units

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}
MAX_EXAMPLES = 10


def compute(output: str, *, input_text: str, reference: str, options: Optional[dict] = None) -> MetricResult:
    strict = bool((options or {}).get("strict", False))
    segment_units, aligned = units(input_text, output, reference)

    n_correct = 0
    modified: list[str] = []
    for unit in segment_units:
        source, out, gold = (tokenize(t, strict) for t in unit.texts)
        correct = unchanged_positions(source, gold)
        kept_by_model = unchanged_positions(source, out)
        n_correct += len(correct)
        modified.extend(source[i] for i in sorted(correct - kept_by_model))

    details = {
        "correct_words": n_correct,
        "modified_correct_words": len(modified),
        "segment_aligned": aligned,
        "examples": modified[:MAX_EXAMPLES],
    }
    return MetricResult(len(modified) / n_correct if n_correct else None, details)
