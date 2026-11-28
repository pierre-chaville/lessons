"""wer_rendered (level C): word error rate of the text the reader sees. Replaces wer / wer_fold for
the transcripts corrected in Hebrew script.

The gold and the output go through the same rendering as the app display (metrics/hebrew.render,
mirror of the frontend renderHebrewTerms): each Hebrew expression found in the glossary of the app
DB is shown in the primary form of the display settings (default `translit`: its transliteration,
long quotations stay in Hebrew); other Hebrew words stay as written. Words are then compared as
wer_fold: Latin words folded (text.fold: case, accents, transliteration variants, scholarly
letters ḥ ʿ ʾ), Hebrew words without points. A Latin word facing a Hebrew word with the same
consonants (Pessaḥ / פֶּסַח, when פֶּסַח has no glossary transliteration) is not an error.
Computed segment by segment when the output keeps the segments of corrected.md.

The scores depend on the glossary: its size and the number of expressions rendered are in the details.

Options: primary (translit | vocalized | unvocalized, default translit), quotations_in_hebrew
(default true), glossary (default true; false: Hebrew words are compared as written).
"""

from __future__ import annotations

from typing import Optional

from bench.dataset import _format_seconds
from bench.metrics import MetricResult
from bench.metrics.hebrew import (PRIMARY_FORMS, blocks, check_glossary_option, cross_script_matches, load_glossary,
                                  render, rendered_key, tokens)
from bench.metrics.text import ErrorCounts, units

HIGHER_IS_BETTER = False
PERCENT = True
REPORT_DETAILS: dict[str, bool] = {}
WORST_SEGMENTS = 5


def check_options(options: dict) -> list[str]:
    problems = check_glossary_option(options)
    if options.get("primary", "translit") not in PRIMARY_FORMS:
        problems.append(f"'primary' must be one of {list(PRIMARY_FORMS)}, got {options.get('primary')!r}")
    if not isinstance(options.get("quotations_in_hebrew", True), bool):
        problems.append("'quotations_in_hebrew' must be true or false")
    return problems


def _counts(gold, out) -> ErrorCounts:
    """Edit operations, a Hebrew / Latin pair with the same consonants inside a block of differences
    not counted."""
    counts = ErrorCounts(ref_length=len(gold), hyp_length=len(out))
    for equal, g_start, g_end, o_start, o_end in blocks([rendered_key(t) for t in gold], [rendered_key(t) for t in out]):
        if equal:
            continue
        same = cross_script_matches(gold[g_start:g_end], out[o_start:o_end])
        n_gold, n_out = g_end - g_start - same, o_end - o_start - same
        counts.substitutions += min(n_gold, n_out)
        counts.deletions += max(n_gold - n_out, 0)
        counts.insertions += max(n_out - n_gold, 0)
    return counts


def compute(output: str, *, input_text: str = "", reference: str, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    glossary = load_glossary(bool(options.get("glossary", True)))
    primary = options.get("primary", "translit")
    in_hebrew = bool(options.get("quotations_in_hebrew", True))
    segment_units, aligned = units(reference, output)
    total = ErrorCounts()
    rendered_gold = rendered_output = 0
    worst = []
    for unit in segment_units:
        gold, n_gold = render(tokens(unit.texts[0]), glossary, primary, in_hebrew)
        out, n_out = render(tokens(unit.texts[1]), glossary, primary, in_hebrew)
        rendered_gold += n_gold
        rendered_output += n_out
        counts = _counts(gold, out)
        total += counts
        if counts.errors:
            worst.append((counts.errors, unit, gold, out))
    worst.sort(key=lambda w: -w[0])
    details = {
        "errors": total.errors,
        "substitutions": total.substitutions,
        "deletions": total.deletions,
        "insertions": total.insertions,
        "ref_length": total.ref_length,
        "output_length": total.hyp_length,
        "segment_aligned": aligned,
        "primary": primary,
        "glossary_entries": glossary.size,
        "glossary_matches_gold": rendered_gold,
        "glossary_matches_output": rendered_output,
        "worst_segments": [
            {"start": unit.start, "time": _format_seconds(unit.start) if unit.start is not None else None,
             "errors": n, "reference": " ".join(t.text for t in gold), "output": " ".join(t.text for t in out)}
            for n, unit, gold, out in worst[:WORST_SEGMENTS]
        ],
    }
    return MetricResult(total.rate(), details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the words of the gold as displayed to the reader (both texts rendered through the glossary)'
