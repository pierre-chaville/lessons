"""Edits made by the model compared with the expected edits.

An edit is a maximal run of changed words in the word diff initial -> text: (span of initial words,
replacement words). Model edits come from initial -> output, expected edits from initial -> gold.
A model edit is correct when the gold has exactly the same edit (same span, same words).

- precision = correct model edits / model edits (None if the model made no edit)
- recall    = correct model edits / expected edits (None if no edit was expected)
- value     = F1 = 2 * correct / (model edits + expected edits) (None if both are 0)

The diff is done segment by segment when the three transcripts keep the same segments.
Options: strict (default false): case and punctuation edits count.
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.text import Edit, edits, tokenize, units

HIGHER_IS_BETTER = True
PERCENT = True
REPORT_DETAILS = {"precision": True, "recall": True}
MAX_EXAMPLES = 10


def _describe(source: list[str], edit: Edit) -> str:
    before = " ".join(source[edit.start : edit.end]) or "∅"
    return f"{before} -> {' '.join(edit.target) or '∅'}"


def compute(output: str, *, input_text: str, reference: str, options: Optional[dict] = None) -> MetricResult:
    strict = bool((options or {}).get("strict", False))
    segment_units, aligned = units(input_text, output, reference)

    model_edits: set[tuple[int, Edit]] = set()
    gold_edits: set[tuple[int, Edit]] = set()
    sources: dict[int, list[str]] = {}
    for unit in segment_units:
        source, out, gold = (tokenize(t, strict) for t in unit.texts)
        sources[unit.index] = source
        model_edits.update((unit.index, e) for e in edits(source, out))
        gold_edits.update((unit.index, e) for e in edits(source, gold))

    correct = model_edits & gold_edits
    n_model, n_gold, n_correct = len(model_edits), len(gold_edits), len(correct)

    def examples(found: set[tuple[int, Edit]]) -> list[str]:
        ordered = sorted(found, key=lambda x: (x[0], x[1].start, x[1].end))
        return [_describe(sources[i], e) for i, e in ordered[:MAX_EXAMPLES]]

    details = {
        "precision": n_correct / n_model if n_model else None,
        "recall": n_correct / n_gold if n_gold else None,
        "model_edits": n_model,
        "expected_edits": n_gold,
        "correct_edits": n_correct,
        "segment_aligned": aligned,
        "missed": examples(gold_edits - correct),
        "wrong": examples(model_edits - correct),
    }
    f1 = 2 * n_correct / (n_model + n_gold) if (n_model + n_gold) else None
    return MetricResult(f1, details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% (F1 of the model edits vs the expected edits)'
DETAIL_DOCS = {
    'precision': 'Share of the edits made by the model that are exactly the expected edit (same span, same words). Unit: % of the model edits.',
    'recall': 'Share of the expected edits (initial -> gold) that the model made exactly. Unit: % of the expected edits.',
}
