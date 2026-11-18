"""idea_coverage (judge): share of the ideas of edited_ideas.yaml found in the edited output.

One judge call: for each idea, `present` / `partial` / `absent` with a verbatim quote of the output.
Evidence check: a present / partial verdict whose quote is not found in the output (fuzzy match,
`evidence_threshold`, default 85) is rejected and counted as absent.

Value = Σ(weight × verdict) / Σ(weight), present = 1, partial = 0.5, absent = 0, weights high = 3,
medium = 2, low = 1. Details: counts, unweighted coverage, the missed high-importance ideas
(`missed_high`), rejected evidence and the verdicts.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from bench import steps
from bench.dataset import IMPORTANCE_WEIGHTS
from bench.judge import DEFAULT_EVIDENCE_THRESHOLD, normalize_for_quotes, quote_found
from bench.metrics import MetricResult

JUDGE = True
VERSION = 1
HIGHER_IS_BETTER = True
REPORT_DETAILS = {"missed_high": False}
PERCENT = True
PERCENT_DETAILS: set[str] = set()
DIGITS = 1
NEEDS_REFERENCE = False

VALUES = {"present": 1.0, "partial": 0.5, "absent": 0.0}

PROMPT = """You evaluate the edited version of a Jewish studies lesson given in French.
Below are the ideas the edited version is expected to contain, then the edited version.

For each idea, answer:
- `present`: the idea is clearly expressed (the wording may differ);
- `partial`: only part of the idea is expressed, or it is vague or distorted;
- `absent`: the idea is not expressed.

For `present` and `partial`, give `quote`: an exact excerpt of the edited version (one or two
sentences, copied character for character, in French) that expresses the idea. For `absent`, an
empty quote. Give exactly one verdict per idea id.

Ideas:
{ideas}

Edited version:
{output}
"""


class IdeaVerdict(BaseModel):
    id: int = Field(description="Id of the idea.")
    verdict: Literal["present", "partial", "absent"]
    quote: str = Field(description="Exact excerpt of the edited version; empty when absent.")


class IdeaVerdicts(BaseModel):
    verdicts: list[IdeaVerdict]


def check_options(options: dict) -> list[str]:
    threshold = options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
        return [f"'evidence_threshold' must be between 0 and 100, got {threshold!r}"]
    return []


def _ideas_text(ideas: list[dict]) -> str:
    return "\n".join(f"{idea['id']}. {idea['text']}" for idea in ideas)


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    ideas = item.ideas or []
    tokens_in = steps.approx_tokens(PROMPT) + steps.approx_tokens(_ideas_text(ideas)) + steps.approx_tokens(output)
    return tokens_in, 60 * len(ideas) + 50


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    options = options or {}
    ideas = (item.ideas if item is not None else None) or []
    if not ideas:
        return MetricResult(None, {"ideas": 0})
    threshold = float(options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD))
    parsed = judge.ask(IdeaVerdicts, PROMPT.format(ideas=_ideas_text(ideas), output=output))
    by_id = {v.id: v for v in parsed.verdicts}
    normalized_output = normalize_for_quotes(output)

    weighted = total_weight = 0.0
    counts = {"present": 0, "partial": 0, "absent": 0}
    rejected, missing, missed_high, verdicts = [], [], [], []
    for idea in ideas:
        verdict = by_id.get(idea["id"])
        label, quote = (verdict.verdict, verdict.quote.strip()) if verdict else ("absent", "")
        if verdict is None:
            missing.append(idea["id"])
        elif label != "absent" and not quote_found(quote, normalized_output, threshold):
            rejected.append(idea["id"])
            label = "absent"
        weight = IMPORTANCE_WEIGHTS.get(idea.get("importance"), 1)
        weighted += weight * VALUES[label]
        total_weight += weight
        counts[label] += 1
        if label == "absent" and idea.get("importance") == "high":
            missed_high.append(idea["text"])
        verdicts.append({"id": idea["id"], "importance": idea.get("importance"), "idea": idea["text"],
                         "verdict": label, "quote": quote[:300]})

    details = {
        "ideas": len(ideas),
        **counts,
        "coverage_unweighted": sum(VALUES[v["verdict"]] for v in verdicts) / len(ideas),
        "missed_high": len(missed_high),
        "missed_high_ideas": missed_high,
        "rejected_evidence": rejected,
        "missing_verdicts": missing,
        "verdicts": verdicts,
    }
    return MetricResult(weighted / total_weight if total_weight else None, details)
