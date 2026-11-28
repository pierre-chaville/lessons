"""idea_coverage (judge): share of the ideas of edited_ideas.yaml found in the edited output.

Judgment (one call, stored and reused): for each idea, its essential elements with a status
(`present` / `implicit` / `distorted` / `missing`), the verdict, `missing` (one sentence on what
is missing or distorted, for partial / absent) and `quotes` (exact excerpts of the output, several
when the idea is expressed in several places). The essential elements come from the `elements`
of the idea in edited_ideas.yaml when given (stable, checked by hand), else the judge breaks the
idea down itself. Rule given to the judge: present = all essential elements explicitly stated;
partial = at least one essential element missing, only implied or distorted; absent = the idea
is no longer recognizable.

Scoring (no call): quotes are located in the output (accents, case, markdown and Hebrew vowel
points ignored, `evidence_threshold`, default 85). A present / partial verdict without any quote
found is counted as absent (`rejected_evidence`); a present verdict with an element that is not
present is counted as partial (`downgraded`): the rule is applied by code, not trusted to the judge.

Value = Σ(weight × verdict) / Σ(weight), present = 1, partial = 0.5, absent = 0, weights high = 3,
medium = 2, low = 1. Details: distribution of the verdicts (present_rate / partial_rate /
absent_rate: a metric where every good model has ~95 % present is saturated), counts of the
elements, the missed high-importance ideas and the verdicts.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from bench import steps
from bench.dataset import IMPORTANCE_WEIGHTS
from bench.judge import DEFAULT_EVIDENCE_THRESHOLD, QuoteIndex
from bench.metrics import MetricResult

JUDGE = True
VERSION = 2
JUDGE_OPTIONS: set[str] = set()  # evidence_threshold only changes the scoring
HIGHER_IS_BETTER = True
REPORT_DETAILS = {"present_rate": True, "partial_rate": None, "absent_rate": False, "missed_high": False}
PERCENT = True
PERCENT_DETAILS = {"present_rate", "partial_rate", "absent_rate"}
DIGITS = 1
NEEDS_REFERENCE = False

VALUES = {"present": 1.0, "partial": 0.5, "absent": 0.0}
ELEMENT_STATUSES = ("present", "implicit", "distorted", "missing")

PROMPT = """You evaluate the edited version of a Jewish studies lesson given in French.
Below are the ideas the edited version is expected to contain, then the edited version.

For each idea:
1. `elements`: the essential elements of the idea (what must be said for the idea to be there),
   each in a few words, in French. When the essential elements of an idea are given below, use
   exactly these, in the same order; otherwise break the idea down yourself (usually 2 to 4).
   For each element, `status`: `present` (explicitly stated), `implicit` (only implied or
   suggested), `distorted` (stated with a change of meaning) or `missing`.
2. `verdict`, with this rule:
   - `present`: ALL essential elements are explicitly stated (the wording may differ);
   - `partial`: at least one essential element is missing, only implied or distorted;
   - `absent`: the idea is no longer recognizable.
3. `missing`: for partial and absent, one sentence in French saying precisely what is missing,
   implied or distorted; null for present.
4. `quotes`: the exact excerpts of the edited version that express the idea, copied character
   for character (each one or two sentences, may be shortened with "..."); give several quotes when
   the idea is expressed in several places, never join fragments of different places into one
   quote. Empty list for absent.
Give exactly one verdict per idea id.

Ideas:
{ideas}

Edited version:
{output}
"""


class Element(BaseModel):
    element: str = Field(description="Essential element of the idea, a few words in French.")
    status: Literal["present", "implicit", "distorted", "missing"]


class IdeaVerdict(BaseModel):
    id: int = Field(description="Id of the idea.")
    elements: list[Element]
    verdict: Literal["present", "partial", "absent"]
    missing: Optional[str] = Field(description="What is missing / implied / distorted (French); null if present.")
    quotes: list[str] = Field(description="Exact excerpts of the edited version; empty when absent.")


class IdeaVerdicts(BaseModel):
    verdicts: list[IdeaVerdict]


def check_options(options: dict) -> list[str]:
    threshold = options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
        return [f"'evidence_threshold' must be between 0 and 100, got {threshold!r}"]
    return []


def judge_inputs(item, options: Optional[dict] = None) -> list:
    """The judgment depends on the ideas (text and elements): edited_ideas.yaml changes -> new judgment."""
    return [[i.get("id"), i.get("text"), i.get("elements")] for i in (item.ideas or [])] if item else []


def _ideas_text(ideas: list[dict]) -> str:
    lines = []
    for idea in ideas:
        lines.append(f"{idea['id']}. {idea['text']}")
        if idea.get("elements"):
            lines.append("   essential elements: " + " | ".join(str(e) for e in idea["elements"]))
    return "\n".join(lines)


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    ideas = item.ideas or []
    tokens_in = steps.approx_tokens(PROMPT) + steps.approx_tokens(_ideas_text(ideas)) + steps.approx_tokens(output)
    return tokens_in, 160 * len(ideas) + 50


def judge(output: str, *, input_text: str, item=None, options: Optional[dict] = None, judge=None) -> dict:
    ideas = (item.ideas if item is not None else None) or []
    if not ideas:
        return {"verdicts": []}
    parsed = judge.ask(IdeaVerdicts, PROMPT.format(ideas=_ideas_text(ideas), output=output))
    return {"verdicts": [v.model_dump() for v in parsed.verdicts]}


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    """judge + score (one call)."""
    judgment = globals()["judge"](output, input_text=input_text, item=item, options=options, judge=judge)
    return score(judgment, output, input_text=input_text, item=item, options=options)


def score(judgment: dict, output: str, *, input_text: str, item=None, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    ideas = (item.ideas if item is not None else None) or []
    if not ideas:
        return MetricResult(None, {"ideas": 0})
    threshold = float(options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD))
    by_id = {v["id"]: v for v in judgment.get("verdicts", [])}
    index = QuoteIndex(output)

    weighted = total_weight = 0.0
    counts = {"present": 0, "partial": 0, "absent": 0}
    element_counts = {s: 0 for s in ELEMENT_STATUSES}
    rejected, downgraded, missing_verdicts, missed_high, verdicts = [], [], [], [], []
    for idea in ideas:
        verdict = by_id.get(idea["id"])
        judge_label = verdict["verdict"] if verdict else None
        label = judge_label or "absent"
        elements = (verdict or {}).get("elements") or []
        quotes = []
        for quote in (verdict or {}).get("quotes") or ([verdict["quote"]] if verdict and verdict.get("quote") else []):
            location = index.locate(quote, threshold)
            quotes.append({"text": quote[:400], "found": location is not None,
                           **({"start": location["start"], "end": location["end"]} if location else {})})
        if verdict is None:
            missing_verdicts.append(idea["id"])
        elif label != "absent" and not any(q["found"] for q in quotes):
            rejected.append(idea["id"])
            label = "absent"
        elif label == "present" and any(e.get("status") != "present" for e in elements):
            downgraded.append(idea["id"])
            label = "partial"
        for element in elements:
            if element.get("status") in element_counts:
                element_counts[element["status"]] += 1
        weight = IMPORTANCE_WEIGHTS.get(idea.get("importance"), 1)
        weighted += weight * VALUES[label]
        total_weight += weight
        counts[label] += 1
        if label == "absent" and idea.get("importance") == "high":
            missed_high.append(idea["text"])
        verdicts.append({
            "id": idea["id"], "importance": idea.get("importance"), "idea": idea["text"],
            "verdict": label, "judge_verdict": judge_label,
            "elements": elements, "elements_source": "dataset" if idea.get("elements") else "judge",
            "missing": (verdict or {}).get("missing") or ("no verdict from the judge" if verdict is None else None),
            "quotes": quotes,
        })

    n = len(ideas)
    details = {
        "ideas": n,
        **counts,
        "present_rate": counts["present"] / n,
        "partial_rate": counts["partial"] / n,
        "absent_rate": counts["absent"] / n,
        "coverage_unweighted": sum(VALUES[v["verdict"]] for v in verdicts) / n,
        "elements": element_counts,
        "missed_high": len(missed_high),
        "missed_high_ideas": missed_high,
        "rejected_evidence": rejected,
        "downgraded": downgraded,
        "missing_verdicts": missing_verdicts,
        "verdicts": verdicts,
    }
    return MetricResult(weighted / total_weight if total_weight else None, details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% (weighted score of the ideas: present = 1, partial = 0.5, absent = 0; weights by importance)'
DETAIL_DOCS = {
    'present_rate': 'Share of the ideas of edited_ideas.yaml fully present (all essential elements explicitly stated). Unit: % of the ideas (unweighted).',
    'partial_rate': 'Share of the ideas partially present (an essential element missing, implied or distorted). Unit: % of the ideas.',
    'absent_rate': 'Share of the ideas no longer recognizable in the output. Unit: % of the ideas.',
    'missed_high': 'High-importance ideas absent from the output. Unit: number of ideas.',
}
