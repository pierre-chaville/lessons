"""correction_judge (judge): impact of the serious discrepancies of a correction on the meaning.

The judge assesses discrepancies, not the whole text:

1. Deterministic filtering first (metrics.hebrew.compare_unit, the function of the other Hebrew
   metrics and of the review app colors): only the red and purple discrepancies are judged
   (`wrong_word`, `latin_uncorrected`, `missing`, `french_error`, `drift`). Variants, word forms,
   Latin script, vowel points and minor differences are never sent.
2. One call per lesson and model (split in batches of `batch_size` discrepancies, default 80), the
   discrepancies grouped by segment with the raw transcription, the gold, the output and the
   previous / next gold segments as context (`context_segments`, default 2).
3. For each discrepancy the judge gives its impact on the edited version (severity 0 none, 1 minor,
   2 significant, 3 critical), `recoverable_from_context`, `who_is_right` (gold / model /
   both_acceptable / unsure) and a short explanation.

Scoring (no call, from the stored judgment): a discrepancy is a model error when the judge says the
gold is right or is unsure; `model` (the output is right, the gold is wrong) is a gold suspect and
`both_acceptable` is not an error. Rates per 1,000 words of the gold:

- value = `weighted_error_score`: sum of the severities of the model errors per 1,000 words
- `critical_errors`, `significant_errors`: model errors of severity 3 / 2 per 1,000 words
- `unrecoverable_rate`: share of the model errors that the edition cannot recover from context
- `gold_suspects`: discrepancies where the output is right rather than the gold (listed in
  `gold_suspect_list`: the gold review queue)

The judgment stores the judged discrepancies with their verdict: it is reused while the output, the
gold (corrected.md) and the judge options are the same. A change of the app glossary does not
trigger a new judgment (the discrepancies judged are those of the judgment time).

Options (all change the judgment): context_segments, batch_size, and the options of the analysis
glossary, case_sensitive, one_letter_variants (as wer_french).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field

from bench import steps
from bench.dataset import _format_seconds, format_transcript, parse_transcript
from bench.metrics import MetricResult
from bench.metrics.hebrew import HE_TOKEN, LABELS, SEVERITIES, analyze, check_glossary_option, doubts
from bench.metrics.text import segment_text

JUDGE = True
VERSION = 1
JUDGE_OPTIONS = {"context_segments", "batch_size", "glossary", "case_sensitive", "one_letter_variants"}
HIGHER_IS_BETTER = False
REPORT_DETAILS = {"critical_errors": False, "significant_errors": False, "unrecoverable_rate": False,
                  "gold_suspects": None}
PERCENT = False
PERCENT_DETAILS = {"unrecoverable_rate"}
DIGITS = 1
NEEDS_REFERENCE = False  # the gold comes from the dataset item (corrected.md)

JUDGED_CATEGORIES = SEVERITIES["error"] + SEVERITIES["drift"]
MODEL_ERROR = ("gold", "unsure")  # who_is_right values counted as an error of the model
TOKENS_PER_VERDICT = 90
WHOLE_TEXT = "whole text"

PROMPT = """You evaluate the automatic correction of the transcription of a Jewish studies lesson given in French
by a Rav. The raw speech-to-text transcription was corrected by a model; a human-reviewed version (the
gold) is the reference. The corrected text is then turned into an edited long-form version of the lesson.
In the correction, Hebrew words and expressions are written in Hebrew script with vowel points (a
transliteration in Latin script of the right word is acceptable but not expected).

Below are the discrepancies between the model output and the gold that a deterministic comparison found
serious, grouped by segment. Harmless differences (spelling variants, vowel points, word forms, Latin
transliteration of the right word) were already filtered out. `⟨HE⟩` stands for a Hebrew passage (the
Hebrew words are compared separately). For each discrepancy, judge its impact on the edited version:

severity:
- 0 none: same meaning, difference in form only (e.g. `Torah` instead of `תּוֹרָה`)
- 1 minor: grammatical or agreement error with no impact on comprehension; the editing stage will
  correct it (e.g. `dit` / `disent`, `de l'עֹמֶר`)
- 2 significant: information is lost or a passage becomes unclear, but the intended meaning can be
  recovered from the context (e.g. `l'échappement` left unchanged instead of `שָׁבוּעוֹת`)
- 3 critical: the meaning is altered: a different concept, source or person, or fabricated content;
  the error will propagate as a false statement (e.g. `סְפִירַת הָעֹמֶר` instead of `פֶּסַח`)

recoverable_from_context: true when an editor reading the output alone (without the audio) would
still understand what the Rav meant (a word left unchanged whose meaning is obvious from the
sentence); false when a concept, a source or a person is replaced by another, or content is lost or made up.

who_is_right: `gold` (the gold is right, the output is wrong), `model` (the output is right and the
gold is wrong, e.g. a mistake in the reviewed text: use the raw transcription and the context),
`both_acceptable` (both are correct, e.g. `dit` or `disent` after `חֲזַ״ל`), `unsure`.
Rate the severity of the output whoever is right (0 when the output is right or acceptable).

explanation: one or two sentences in English: what changes in the meaning, and why it is (not) recoverable.

Give exactly one verdict per discrepancy id.

{segments}
"""


class Verdict(BaseModel):
    diff_id: int = Field(description="Id of the discrepancy.")
    severity: Literal[0, 1, 2, 3]
    recoverable_from_context: bool
    who_is_right: Literal["gold", "model", "both_acceptable", "unsure"]
    explanation: str = Field(description="One or two sentences in English.")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


@dataclass
class Discrepancy:
    id: int
    unit: int  # index of the segment
    category: str
    gold: str  # gold words of the discrepancy
    output: str  # output words of the discrepancy
    segment: str  # "1m 53s - 1m 55s"

    @property
    def label(self) -> str:
        return f"{LABELS[self.category]}: {self.gold or '∅'} → {self.output or '∅'}"


def check_options(options: dict) -> list[str]:
    problems = check_glossary_option(options)
    for name in ("case_sensitive", "one_letter_variants"):
        if not isinstance(options.get(name, False), bool):
            problems.append(f"'{name}' must be true or false")
    for name, minimum in (("context_segments", 0), ("batch_size", 1)):
        value = options.get(name, minimum)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            problems.append(f"'{name}' must be an integer >= {minimum}, got {value!r}")
    return problems


def _gold(item) -> str:
    return format_transcript((item.corrected if item is not None else None) or [])


def judge_inputs(item, options: Optional[dict] = None) -> str:
    """The judgment depends on the gold: corrected.md changes (e.g. fixed in the review app) -> new judgment."""
    return hashlib.sha256(_gold(item).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Discrepancies
# --------------------------------------------------------------------------- #


def _words(words: list[str]) -> str:
    return " ".join("[Hebrew]" if w == HE_TOKEN else w for w in words)


@dataclass
class UnitDiscrepancy:
    """A red / purple discrepancy of one segment, with the Term / FrenchEdit objects it comes from
    (the review app marks their words with the verdict)."""

    position: int  # output index (order in the segment)
    category: str
    gold: str
    output: str
    sources: tuple

    @property
    def key(self) -> tuple[str, str, str]:
        """Identifies the discrepancy within its segment (verdicts are matched on it)."""
        return self.category, self.gold, self.output


def unit_discrepancies(unit) -> list[UnitDiscrepancy]:
    """The discrepancies of one segment (metrics.hebrew.UnitAnalysis) sent to the judge, in order."""
    missing = [t for t in unit.terms if t.category == "missing"]
    items = [UnitDiscrepancy(t.output_index if t.output_index is not None else t.gap_at, t.category, t.gold,
                             t.output or "", (t,))
             for t in unit.terms if t.category in JUDGED_CATEGORIES and t.category != "missing"]
    for edit in unit.edits:
        if edit.category not in JUDGED_CATEGORIES:
            continue
        first = edit.output_tokens[0] if edit.output_tokens else edit.gap_at
        last = edit.output_tokens[-1] + 1 if edit.output_tokens else edit.gap_at
        # A Hebrew passage replaced by French words is one discrepancy: the missing Hebrew words
        # at that place take the ⟨HE⟩ tokens of the edit.
        inside = [t for t in missing if first <= t.gap_at <= last]
        words, sources = [], [edit]
        for word in edit.gold:
            if word == HE_TOKEN and inside:
                term = inside.pop(0)
                missing.remove(term)
                sources.append(term)
                words.append(term.gold)
            else:
                words.append(word)
        items.append(UnitDiscrepancy(first, edit.category, _words(words), _words(edit.output), tuple(sources)))
    items += [UnitDiscrepancy(t.gap_at, "missing", t.gold, "", (t,)) for t in missing]
    return sorted(items, key=lambda d: d.position)


def segment_label(start: int, end: int) -> str:
    return f"{_format_seconds(start)} - {_format_seconds(end)}"


def discrepancies(output: str, gold: str, input_text: str, options: dict):
    """(analysis, red and purple discrepancies) of an output, numbered from 1."""
    analysis = analyze(output, gold, input_text or "", bool(options.get("glossary", True)),
                       bool(options.get("case_sensitive", False)), bool(options.get("one_letter_variants", True)))
    gold_segments, _ = parse_transcript(gold)
    found: list[Discrepancy] = []
    for index, unit in enumerate(analysis.units):
        segment = gold_segments[index] if analysis.segment_aligned else None
        label = segment_label(segment.start, segment.end) if segment else WHOLE_TEXT
        for d in unit_discrepancies(unit):
            found.append(Discrepancy(len(found) + 1, index, d.category, d.gold, d.output, label))
    return analysis, found


def _doubt_lines(raw: str) -> list[str]:
    clean, spans = doubts(raw)
    lines = []
    for span in spans:
        alternatives = span.attributes.get("alt")
        lines.append(f"  (the reviewer was unsure of «{clean[span.start:span.end]}»"
                     + (f"; alternatives: {' | '.join(alternatives.split('|'))})" if alternatives else ")"))
    return lines


def _segments_text(found: list[Discrepancy], gold: str, output: str, input_text: str, context: int) -> str:
    gold_segments, _ = parse_transcript(gold)
    output_segments, _ = parse_transcript(output)
    initial = {s.start: s.text for s in parse_transcript(input_text or "")[0]}
    blocks = []
    for unit in sorted({d.unit for d in found}):
        own = [d for d in found if d.unit == unit]
        if own[0].segment == WHOLE_TEXT:  # output not segment-aligned: whole texts
            lines = ["### Whole text", f"gold: {segment_text(gold)}", f"output: {segment_text(output)}"]
        else:
            g = gold_segments[unit]
            lines = [f"### Segment [{own[0].segment}]"]
            for s in gold_segments[max(0, unit - context):unit]:
                lines.append(f"previous (gold): {segment_text(s.text)}")
            if g.start in initial:
                lines.append(f"raw transcription: {segment_text(initial[g.start])}")
            lines.append(f"gold: {segment_text(g.text)}")
            lines += _doubt_lines(g.text)
            lines.append(f"output: {segment_text(output_segments[unit].text)}")
            for s in gold_segments[unit + 1:unit + 1 + context]:
                lines.append(f"next (gold): {segment_text(s.text)}")
        lines.append("discrepancies:")
        lines += [f"  {d.id}. {d.label}" for d in own]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _batches(found: list[Discrepancy], size: int) -> list[list[Discrepancy]]:
    """Batches of about `size` discrepancies, a segment never split."""
    batches: list[list[Discrepancy]] = [[]]
    for unit in sorted({d.unit for d in found}):
        own = [d for d in found if d.unit == unit]
        if batches[-1] and len(batches[-1]) + len(own) > size:
            batches.append([])
        batches[-1].extend(own)
    return [b for b in batches if b]


# --------------------------------------------------------------------------- #
# Judge and score
# --------------------------------------------------------------------------- #


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    options = options or {}
    gold = _gold(item)
    context = int(options.get("context_segments", 2))
    if output.strip() == gold.strip():  # not generated yet (estimated from the gold): assume 1 segment in 8
        segments, _ = parse_transcript(gold)
        n_segments = max(1, len(segments) // 8)
        per_segment = sum(steps.approx_tokens(s.text) for s in segments) / max(1, len(segments))
        tokens_in = steps.approx_tokens(PROMPT) + int(n_segments * per_segment * (4 + 2 * context))
        return tokens_in, n_segments * 2 * TOKENS_PER_VERDICT
    _, found = discrepancies(output, gold, input_text, options)
    if not found:
        return 0, 0
    batches = _batches(found, int(options.get("batch_size", 80)))
    text = _segments_text(found, gold, output, input_text, context)
    return steps.approx_tokens(PROMPT) * len(batches) + steps.approx_tokens(text), len(found) * TOKENS_PER_VERDICT


def judge(output: str, *, input_text: str, item=None, options: Optional[dict] = None, judge=None) -> dict:
    options = options or {}
    gold = _gold(item)
    analysis, found = discrepancies(output, gold, input_text, options)
    words = sum(len(u.gold) for u in analysis.units)
    verdicts: list[dict] = []
    context = int(options.get("context_segments", 2))
    for batch in _batches(found, int(options.get("batch_size", 80))):
        prompt = PROMPT.format(segments=_segments_text(batch, gold, output, input_text, context))
        verdicts += [v.model_dump() for v in judge.ask(Verdicts, prompt).verdicts]
    return {
        "gold_words": words,
        "discrepancies": [{"id": d.id, "segment": d.segment, "category": d.category, "gold": d.gold,
                           "output": d.output} for d in found],
        "verdicts": verdicts,
    }


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    """judge + score."""
    judgment = globals()["judge"](output, input_text=input_text, item=item, options=options, judge=judge)
    return score(judgment, output, input_text=input_text, item=item, options=options)


def score(judgment: dict, output: str, *, input_text: str, item=None, options: Optional[dict] = None) -> MetricResult:
    words = judgment.get("gold_words") or 0
    if not words:
        return MetricResult(None, {"gold_words": 0})
    per_1000 = 1000 / words
    by_id = {v["diff_id"]: v for v in judgment.get("verdicts", [])}
    severity_counts = {str(s): 0 for s in range(4)}
    who = {"gold": 0, "model": 0, "both_acceptable": 0, "unsure": 0}
    weighted = unrecoverable = model_errors = 0
    judged, missing, suspects = [], [], []
    for d in judgment.get("discrepancies", []):
        verdict = by_id.get(d["id"])
        if verdict is None:
            missing.append(d["id"])
            continue
        who[verdict["who_is_right"]] += 1
        entry = {**d, **{k: verdict[k] for k in ("severity", "recoverable_from_context", "who_is_right",
                                                  "explanation")}}
        entry["model_error"] = verdict["who_is_right"] in MODEL_ERROR
        judged.append(entry)
        if verdict["who_is_right"] == "model":
            suspects.append(entry)
        if not entry["model_error"]:
            continue
        model_errors += 1
        severity_counts[str(verdict["severity"])] += 1
        weighted += verdict["severity"]
        unrecoverable += not verdict["recoverable_from_context"]
    details = {
        "gold_words": words,
        "discrepancies": len(judgment.get("discrepancies", [])),
        "model_errors": model_errors,
        "critical_errors": severity_counts["3"] * per_1000,
        "significant_errors": severity_counts["2"] * per_1000,
        "unrecoverable_rate": unrecoverable / model_errors if model_errors else 0.0,
        "gold_suspects": len(suspects),
        "severity_counts": severity_counts,
        "who_is_right": who,
        "missing_verdicts": missing,
        "gold_suspect_list": suspects,
        "verdicts": sorted(judged, key=lambda e: (-e["severity"] * e["model_error"], e["id"])),
    }
    return MetricResult(weighted * per_1000, details)
