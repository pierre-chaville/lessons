"""faithfulness (judge): share of the claims of the output that come from the lesson.

1. The judge splits the output into atomic claims (one call; always the same judge model, so that
   all candidates are split the same way).
2. The claims are checked against the step input (corrected.md for edition, edited.md for summary),
   by batches of `claims_per_call` (default 30): `supported`, `external_addition` (possibly true but
   not said in the lesson), `extrapolation`, `misattribution` (e.g. Rashi instead of Ramban),
   `contradicted`, with a verbatim quote of the source for supported / misattribution / contradicted.
   Evidence check: a `supported` verdict whose quote is not found in the source (fuzzy match,
   `evidence_threshold`, default 85) becomes `unverified`.

Value = supported claims / claims. Details: counts per verdict (contradicted and misattribution
are the most serious) and the claims that are not supported.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field

from bench import steps
from bench.judge import DEFAULT_EVIDENCE_THRESHOLD, normalize_for_quotes, quote_found
from bench.metrics import MetricResult
from bench.metrics.text import count_words, plain_text

JUDGE = True
VERSION = 1
HIGHER_IS_BETTER = True
REPORT_DETAILS = {"claims": None, "contradicted": False, "misattribution": False}
PERCENT = True
PERCENT_DETAILS: set[str] = set()
DIGITS = 1
NEEDS_REFERENCE = False

DEFAULT_CLAIMS_PER_CALL = 30
VERDICTS = ("supported", "external_addition", "extrapolation", "misattribution", "contradicted")
MAX_REPORTED = 40

SPLIT_PROMPT = """Split the following text (the edited version of a Jewish studies lesson, in French)
into atomic claims. A claim is one self-contained statement of content: a fact, an interpretation,
a teaching, an attribution to a source, a book or a person. Ignore rhetoric, transitions, headings
and questions to the audience. Write each claim in French, in one short sentence that can be
understood alone (replace pronouns by what they refer to). Keep the order of the text.

Text:
{output}
"""

CHECK_PROMPT = """You check whether claims extracted from the edited version of a Jewish studies lesson
come from the lesson itself. Judge each claim against the source below ONLY, not against your
own knowledge:
- `supported`: said or directly implied in the source;
- `external_addition`: not said in the lesson (even if it may be true);
- `extrapolation`: goes beyond what is said (generalization, stronger or different conclusion);
- `misattribution`: attributes a teaching or a quote to the wrong source, book or person;
- `contradicted`: the source says otherwise.

For `supported`, `misattribution` and `contradicted`, give `quote`: an exact excerpt of the source
(copied character for character, in French) on which the verdict relies. Otherwise an empty quote.
Give exactly one verdict per claim id.

Source (transcript of the lesson):
{source}

Claims:
{claims}
"""


class Claims(BaseModel):
    claims: list[str] = Field(description="Atomic claims, in French, in the order of the text.")


class ClaimVerdict(BaseModel):
    id: int = Field(description="Id of the claim.")
    verdict: Literal["supported", "external_addition", "extrapolation", "misattribution", "contradicted"]
    quote: str = Field(description="Exact excerpt of the source; empty when not needed.")


class ClaimVerdicts(BaseModel):
    verdicts: list[ClaimVerdict]


def check_options(options: dict) -> list[str]:
    problems = []
    threshold = options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
        problems.append(f"'evidence_threshold' must be between 0 and 100, got {threshold!r}")
    per_call = options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL)
    if not isinstance(per_call, int) or per_call < 1:
        problems.append(f"'claims_per_call' must be a positive integer, got {per_call!r}")
    return problems


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    """Split call + check calls (about one claim per 18 words of output, 60 tokens per verdict)."""
    output_tokens = steps.approx_tokens(output)
    source_tokens = steps.approx_tokens(plain_text(input_text or ""))
    claims = max(1, count_words(output) // 18)
    claim_tokens = claims * 25
    calls = math.ceil(claims / int(options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL)))
    tokens_in = (steps.approx_tokens(SPLIT_PROMPT) + output_tokens
                 + calls * (steps.approx_tokens(CHECK_PROMPT) + source_tokens) + claim_tokens)
    return tokens_in, claim_tokens + 60 * claims


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    options = options or {}
    threshold = float(options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD))
    per_call = int(options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL))
    source = plain_text(input_text or "")
    if not output.strip() or not source.strip():
        return MetricResult(None, {"claims": 0})

    claims = [c.strip() for c in judge.ask(Claims, SPLIT_PROMPT.format(output=output)).claims if c.strip()]
    if not claims:
        return MetricResult(None, {"claims": 0})

    normalized_source = normalize_for_quotes(source)
    results: list[dict] = []
    for start in range(0, len(claims), per_call):
        batch = claims[start:start + per_call]
        listing = "\n".join(f"{start + i + 1}. {c}" for i, c in enumerate(batch))
        parsed = judge.ask(ClaimVerdicts, CHECK_PROMPT.format(source=source, claims=listing))
        by_id = {v.id: v for v in parsed.verdicts}
        for i, claim in enumerate(batch):
            claim_id = start + i + 1
            verdict = by_id.get(claim_id)
            if verdict is None:
                label, quote = "missing", ""
            else:
                label, quote = verdict.verdict, verdict.quote.strip()
                if label == "supported" and not quote_found(quote, normalized_source, threshold):
                    label = "unverified"
            results.append({"id": claim_id, "claim": claim, "verdict": label, "quote": quote[:300]})

    counts = {v: 0 for v in (*VERDICTS, "unverified", "missing")}
    for r in results:
        counts[r["verdict"]] += 1
    issues = [r for r in results if r["verdict"] != "supported"]
    issues.sort(key=lambda r: ["contradicted", "misattribution", "extrapolation", "external_addition",
                               "unverified", "missing"].index(r["verdict"]))
    details = {"claims": len(results), **counts, "issues": issues[:MAX_REPORTED]}
    return MetricResult(counts["supported"] / len(results), details)
