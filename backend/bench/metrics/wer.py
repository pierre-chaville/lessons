"""Word error rate between the output and the gold transcript.

value: (substitutions + deletions + insertions) / words of the reference, on the whole extract.
When the output keeps the segments of the reference, the same rate is also computed segment by
segment (total errors / total words): it is higher when words moved across segments.

Options: strict (default false): compare raw words (case and punctuation count).
"""

from __future__ import annotations

from typing import Optional

from bench.metrics import MetricResult
from bench.metrics.text import ErrorCounts, error_counts, normalize, tokenize, units

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}
WORST_SEGMENTS = 5


def error_rate(output: str, reference: str, *, chars: bool, options: Optional[dict] = None) -> MetricResult:
    strict = bool((options or {}).get("strict", False))

    def sequence(text: str):
        return normalize(text, strict) if chars else tokenize(text, strict)

    segment_units, aligned = units(reference, output)
    whole_ref = " ".join(u.texts[0] for u in segment_units)
    whole_out = " ".join(u.texts[1] for u in segment_units)
    whole = error_counts(sequence(whole_ref), sequence(whole_out))

    details = {
        "errors": whole.errors,
        "substitutions": whole.substitutions,
        "deletions": whole.deletions,
        "insertions": whole.insertions,
        "ref_length": whole.ref_length,
        "output_length": whole.hyp_length,
        "segment_aligned": aligned,
        "per_segment_rate": None,
    }
    if aligned:
        total = ErrorCounts()
        worst = []
        for unit in segment_units:
            ref, out = sequence(unit.texts[0]), sequence(unit.texts[1])
            counts = error_counts(ref, out)
            total += counts
            if counts.errors:
                worst.append((counts.errors, unit, ref, out))
        details["per_segment_rate"] = total.rate()
        details["per_segment_errors"] = total.errors
        worst.sort(key=lambda w: -w[0])
        details["worst_segments"] = [
            {
                "index": unit.index,
                "start": unit.start,
                "errors": n,
                "reference": ref if chars else " ".join(ref),
                "output": out if chars else " ".join(out),
            }
            for n, unit, ref, out in worst[:WORST_SEGMENTS]
        ]
    return MetricResult(whole.rate(), details)


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    return error_rate(output, reference, chars=False, options=options)
