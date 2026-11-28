"""faithfulness (judge): share of the claims of the output that are not penalized by the policy.

The judge reports findings, the campaign decides what to penalize.

Judgment (LLM calls, stored and reused):
1. split: the output is split into atomic claims, each with `output_quote`, the exact excerpt of
   the output it comes from (one call; always the same judge model).
2. check: by batches of `claims_per_call` (default 30), each claim against the step input
   (corrected.md for edition, edited.md for summary): verdict, subtype, `source_quote` (closest
   passage of the source, also for negative verdicts; null = nothing related found), one-sentence
   `explanation`, severity (minor / major), `believes` (when an attribution differs: speaker /
   output / unsure) and `reference` (precise reference cited by the output, Sefaria format).
3. references (`verify_references`, default true): the references of the added references / quotes
   and of the misattributions are fetched from Sefaria (bench/sefaria.py) and one call checks that
   the text matches what the output says. A reference that does not exist or does not match becomes
   `wrong_reference` (major); a verified misattribution becomes `speaker_corrected` (the judge's
   opinion on who is right is not trusted alone).

Scoring (no call, re-done at every scoring phase): claims are classified into categories:
supported, unverified (supported but the source quote is not found in the source), missing (no
verdict), reference_added, quote_added, content_added, speaker_corrected, model_error,
wrong_reference, extrapolation, contradicted. Value = 1 - penalized claims / claims, with
`penalize` (default DEFAULT_PENALIZE) the categories penalized; the others are reported only.
Changing `penalize` / `report_only` / `evidence_threshold` re-scores without judge call.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field

from bench import sefaria, steps
from bench.dataset import _format_seconds, parse_transcript
from bench.judge import DEFAULT_EVIDENCE_THRESHOLD, QuoteIndex
from bench.metrics import MetricResult
from bench.metrics.text import count_words, plain_text, strip_speaker_tag

JUDGE = True
VERSION = 2
JUDGE_OPTIONS = {"claims_per_call", "verify_references"}
HIGHER_IS_BETTER = True
REPORT_DETAILS = {"claims": None, "penalized": False, "reported": None, "major": False, "wrong_reference": False}
PERCENT = True
PERCENT_DETAILS: set[str] = set()
DIGITS = 1
NEEDS_REFERENCE = False

DEFAULT_CLAIMS_PER_CALL = 30
EXTERNAL_SUBTYPES = ("reference_added", "quote_added", "content_added")
MISATTRIBUTION_SUBTYPES = ("speaker_corrected", "model_error")
CATEGORIES = ("supported", "unverified", "missing", *EXTERNAL_SUBTYPES, *MISATTRIBUTION_SUBTYPES,
              "wrong_reference", "extrapolation", "contradicted")
DEFAULT_PENALIZE = ("content_added", "model_error", "wrong_reference", "contradicted", "extrapolation", "unverified")
# Order of the issues in the details (most serious first).
ISSUE_ORDER = ("wrong_reference", "contradicted", "model_error", "content_added", "extrapolation", "unverified",
               "speaker_corrected", "quote_added", "reference_added", "missing")
REFERENCE_CHECKED = {"reference_added", "quote_added", "speaker_corrected", "model_error"}

SPLIT_PROMPT = """Split the following text (the edited version of a Jewish studies lesson, in French)
into atomic claims. A claim is one self-contained statement of content: a fact, an interpretation,
a teaching, an attribution to a source, a book, a verse or a person, a quotation of a text. Ignore
rhetoric, transitions, headings and questions to the audience. Write each claim in French, in one
short sentence that can be understood alone (replace pronouns by what they refer to). Keep the
order of the text. For each claim, give `output_quote`: the exact excerpt of the text the claim
comes from, copied character for character (one sentence or less; it may be shortened with "...").

Text:
{output}
"""

CHECK_PROMPT = """You check claims extracted from the edited version of a Jewish studies lesson (in French)
against the transcript of the lesson (the source). Judge against the source ONLY, not against your
own knowledge (except for `believes`).

For each claim give:
- `verdict`:
  - `supported`: said or directly implied in the source;
  - `external_addition`: something the lesson does not say;
  - `extrapolation`: goes beyond what is said (generalization, stronger or different conclusion);
  - `misattribution`: the source attributes the teaching, verse or quotation to another book,
    verse, commentator or person;
  - `contradicted`: the source says otherwise.
- `subtype`:
  - for external_addition: `reference_added` (the Rav quotes or alludes to a text and the edited
    version adds its precise reference, e.g. "(Tehilim 66, 12)"), `quote_added` (the edited version
    adds the text of a verse or source the Rav only alludes to), `content_added` (an idea, an
    explanation, an example, a source or a commentator that is not in the lesson);
  - for misattribution: `speaker_corrected` (you believe the Rav's attribution is wrong and the
    edited version corrects it), `model_error` (the edited version wrongly attributes something the
    Rav attributed correctly, or you cannot tell);
  - null for the other verdicts.
- `source_quote`: ALWAYS, also for negative verdicts, the passage of the source closest to the
  claim, copied character for character (one or two sentences, may be shortened with "...");
  null only if nothing in the source is related to the claim.
- `explanation`: except for supported, one sentence in French saying precisely what differs between
  the claim and the source (e.g. "Le Rav attribue le verset aux Tehilim ; la version éditée
  l'attribue à Osée 14, 3."). Empty for supported.
- `severity`: `major` when it changes the teaching or misleads the reader (invented teaching,
  teaching attributed to the wrong person, contradiction), `minor` otherwise (added reference,
  small precision). `minor` for supported.
- `believes`: when an attribution or a reference differs between the source and the edited version,
  who you believe is right according to your knowledge: `speaker` (the Rav), `output` (the edited
  version) or `unsure`. Null otherwise.
- `reference`: when the claim cites a precise reference (verse, chapter, Talmud page...) that the
  Rav did not give or gave differently, that reference in Sefaria English format ("Hosea 14:3",
  "Psalms 66:12", "Genesis 1:27", "Berakhot 5a"); for a commentary, the reference of the commentary
  itself ("Rashi on Exodus 19:2", "Ramban on Genesis 2:18"); null otherwise.
Give exactly one verdict per claim id.

Source (transcript of the lesson):
{source}

Claims:
{claims}
"""

REFERENCE_PROMPT = """Claims of the edited version of a Jewish studies lesson (in French) cite references.
For each item, the text of the cited reference is given from Sefaria (Hebrew and English). Say
whether the reference contains what the edited version says or quotes:
- `matches`: the quoted text or idea is in this reference;
- `partial`: related but not exactly (neighboring verse, loose paraphrase, only part of it);
- `differs`: the reference does not contain what the edited version says.
Give `explanation`: one sentence in French.

{items}
"""


class Claim(BaseModel):
    claim: str = Field(description="Atomic claim, in French.")
    output_quote: str = Field(description="Exact excerpt of the text the claim comes from.")


class Claims(BaseModel):
    claims: list[Claim]


class ClaimVerdict(BaseModel):
    id: int = Field(description="Id of the claim.")
    verdict: Literal["supported", "external_addition", "extrapolation", "misattribution", "contradicted"]
    subtype: Optional[Literal["reference_added", "quote_added", "content_added", "speaker_corrected", "model_error"]]
    source_quote: Optional[str] = Field(description="Closest passage of the source, exact copy; null if none.")
    explanation: str = Field(description="One sentence in French; empty for supported.")
    severity: Literal["minor", "major"]
    believes: Optional[Literal["speaker", "output", "unsure"]]
    reference: Optional[str] = Field(description="Reference cited by the claim, Sefaria English format; or null.")


class ClaimVerdicts(BaseModel):
    verdicts: list[ClaimVerdict]


class ReferenceCheck(BaseModel):
    id: int
    match: Literal["matches", "partial", "differs"]
    explanation: str


class ReferenceChecks(BaseModel):
    checks: list[ReferenceCheck]


def check_options(options: dict) -> list[str]:
    problems = []
    threshold = options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD)
    if not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
        problems.append(f"'evidence_threshold' must be between 0 and 100, got {threshold!r}")
    per_call = options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL)
    if not isinstance(per_call, int) or per_call < 1:
        problems.append(f"'claims_per_call' must be a positive integer, got {per_call!r}")
    lists = {}
    for key in ("penalize", "report_only"):
        values = options.get(key, [])
        if not isinstance(values, list):
            problems.append(f"'{key}' must be a list of categories")
            continue
        unknown = [v for v in values if v not in CATEGORIES or v == "supported"]
        if unknown:
            problems.append(f"'{key}': unknown categories {unknown} (allowed: {', '.join(CATEGORIES[1:])})")
        lists[key] = set(values)
    both = lists.get("penalize", set()) & lists.get("report_only", set())
    if both:
        problems.append(f"categories both penalized and report_only: {sorted(both)}")
    return problems


def _source(input_text: str) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Plain source sent to the judge, and the (char start, char end, start s, end s) of its segments."""
    segments, _ = parse_transcript(input_text or "")
    if not segments:
        return plain_text(input_text or ""), []
    parts, spans, offset = [], [], 0
    for segment in segments:
        text = strip_speaker_tag(segment.text).strip()
        if not text:
            continue
        parts.append(text)
        spans.append((offset, offset + len(text), segment.start, segment.end))
        offset += len(text) + 1
    return " ".join(parts), spans


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    """Split call + check calls (about one claim per 18 words of output, 150 tokens per verdict)."""
    output_tokens = steps.approx_tokens(output)
    source_tokens = steps.approx_tokens(_source(input_text or "")[0])
    claims = max(1, count_words(output) // 18)
    claim_tokens = claims * 50
    calls = math.ceil(claims / int(options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL)))
    tokens_in = (steps.approx_tokens(SPLIT_PROMPT) + output_tokens
                 + calls * (steps.approx_tokens(CHECK_PROMPT) + source_tokens) + claim_tokens)
    return tokens_in, claim_tokens + 150 * claims


# --------------------------------------------------------------------------- #
# Judgment
# --------------------------------------------------------------------------- #


def _check_references(claims: dict[int, dict], verdicts: list[dict], judge) -> list[dict]:
    to_check = [v for v in verdicts if v.get("reference") and v.get("subtype") in REFERENCE_CHECKED]
    results, items = [], []
    for verdict in to_check:
        text = sefaria.fetch(verdict["reference"])
        entry = {"id": verdict["id"], "reference": verdict["reference"], "slug": text.get("slug"),
                 "found": text.get("found", False), "sefaria_ref": text.get("ref"), "match": None,
                 "explanation": None, "error": text.get("error")}
        results.append(entry)
        if entry["found"]:
            claim = claims.get(verdict["id"], {})
            items.append(f"Item {verdict['id']}:\n- claim: {claim.get('claim')}\n"
                         f"- excerpt of the edited version: {claim.get('output_quote')}\n"
                         f"- cited reference: {verdict['reference']} (Sefaria: {text.get('ref')})\n"
                         f"- Hebrew: {text.get('he', '')[:1500]}\n- English: {text.get('en', '')[:1500]}")
    if items:
        parsed = judge.ask(ReferenceChecks, REFERENCE_PROMPT.format(items="\n\n".join(items)))
        by_id = {c.id: c for c in parsed.checks}
        for entry in results:
            check = by_id.get(entry["id"])
            if check is not None:
                entry["match"], entry["explanation"] = check.match, check.explanation
    return results


def judge(output: str, *, input_text: str, item=None, options: Optional[dict] = None, judge=None) -> dict:
    options = options or {}
    per_call = int(options.get("claims_per_call", DEFAULT_CLAIMS_PER_CALL))
    source = _source(input_text or "")[0]
    if not output.strip() or not source.strip():
        return {"claims": [], "verdicts": [], "references": []}
    parsed = judge.ask(Claims, SPLIT_PROMPT.format(output=output))
    claims = [{"id": i, "claim": c.claim.strip(), "output_quote": c.output_quote.strip()}
              for i, c in enumerate((c for c in parsed.claims if c.claim.strip()), start=1)]
    verdicts: list[dict] = []
    for start in range(0, len(claims), per_call):
        batch = claims[start:start + per_call]
        listing = "\n".join(f"{c['id']}. {c['claim']}" for c in batch)
        result = judge.ask(ClaimVerdicts, CHECK_PROMPT.format(source=source, claims=listing))
        ids = {c["id"] for c in batch}
        verdicts.extend(v.model_dump() for v in result.verdicts if v.id in ids)
    references = []
    if options.get("verify_references", True):
        references = _check_references({c["id"]: c for c in claims}, verdicts, judge)
    return {"claims": claims, "verdicts": verdicts, "references": references}


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    """judge + score."""
    judgment = globals()["judge"](output, input_text=input_text, item=item, options=options, judge=judge)
    return score(judgment, output, input_text=input_text, item=item, options=options)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def _category(verdict: Optional[dict], reference: Optional[dict], source_found: bool) -> str:
    if verdict is None:
        return "missing"
    label = verdict["verdict"]
    if label == "supported":
        return "supported" if source_found else "unverified"
    if reference is not None and (not reference["found"] or reference["match"] == "differs"):
        return "wrong_reference"
    if label == "external_addition":
        return verdict.get("subtype") if verdict.get("subtype") in EXTERNAL_SUBTYPES else "content_added"
    if label == "misattribution":
        if reference is not None and reference["match"] in ("matches", "partial"):
            return "speaker_corrected"
        return verdict.get("subtype") if verdict.get("subtype") in MISATTRIBUTION_SUBTYPES else "model_error"
    return label


def _time(location: Optional[dict], spans: list[tuple[int, int, int, int]]) -> Optional[str]:
    if location is None or not spans:
        return None
    covered = [s for s in spans if s[0] < location["end"] and s[1] > location["start"]]
    if not covered:
        return None
    return f"{_format_seconds(covered[0][2])} - {_format_seconds(covered[-1][3])}"


def score(judgment: dict, output: str, *, input_text: str, item=None, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    threshold = float(options.get("evidence_threshold", DEFAULT_EVIDENCE_THRESHOLD))
    penalize = set(options.get("penalize", DEFAULT_PENALIZE))
    claims = judgment.get("claims") or []
    if not claims:
        return MetricResult(None, {"claims": 0})
    source, spans = _source(input_text or "")
    source_index, output_index = QuoteIndex(source), QuoteIndex(output)
    verdicts = {v["id"]: v for v in judgment.get("verdicts") or []}
    references = {r["id"]: r for r in judgment.get("references") or []}

    counts = {c: 0 for c in CATEGORIES}
    issues, highlights = [], []
    penalized = major = outputs_found = 0
    for claim in claims:
        verdict = verdicts.get(claim["id"])
        reference = references.get(claim["id"])
        source_quote = verdict.get("source_quote") if verdict else None
        source_location = source_index.locate(source_quote, threshold) if source_quote else None
        output_location = output_index.locate(claim.get("output_quote"), threshold)
        category = _category(verdict, reference, source_location is not None)
        counts[category] += 1
        outputs_found += output_location is not None
        is_penalized = category in penalize
        penalized += is_penalized
        severity = "major" if category == "wrong_reference" else (verdict or {}).get("severity")
        if category == "supported":
            continue
        major += severity == "major"
        issue = {
            "id": claim["id"], "claim": claim["claim"], "category": category, "penalized": is_penalized,
            "verdict": (verdict or {}).get("verdict"), "subtype": (verdict or {}).get("subtype"),
            "severity": severity, "explanation": (verdict or {}).get("explanation") or "",
            "believes": (verdict or {}).get("believes"),
            "output_quote": claim.get("output_quote"), "output_found": output_location is not None,
            "source_quote": source_quote, "source_found": source_location is not None,
            "source_time": _time(source_location, spans),
            "reference": reference,
        }
        issues.append(issue)
        if output_location is not None:
            highlights.append({"id": claim["id"], "category": category, "penalized": is_penalized,
                               "start": output_location["start"], "end": output_location["end"]})
    issues.sort(key=lambda i: (not i["penalized"], ISSUE_ORDER.index(i["category"]), i["id"]))
    details = {
        "claims": len(claims),
        "penalized": penalized,
        "reported": len(claims) - counts["supported"] - penalized,
        "major": major,
        **counts,
        "output_quotes_found": outputs_found,
        "issues": issues,
        "highlights": sorted(highlights, key=lambda h: h["start"]),
        "policy": {"penalize": sorted(penalize)},
    }
    return MetricResult(1 - penalized / len(claims), details)


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the claims of the output not penalized by the policy'
DETAIL_DOCS = {
    'claims': 'Atomic claims the judge split the output into (the denominator). Unit: number of claims.',
    'penalized': 'Number of claims in a penalized category (content added, model error, wrong reference, contradicted, extrapolation... per the campaign policy). Unit: number of claims.',
    'reported': 'Number of claims in a category reported but not penalized (e.g. a correct reference added). Unit: number of claims.',
    'major': 'Penalized claims of major severity. Unit: number of claims.',
    'wrong_reference': 'Number of references or quotes added by the output that do not exist on Sefaria or do not say what the output says. Unit: number of references.',
}
