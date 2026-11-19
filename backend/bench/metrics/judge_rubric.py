"""judge_rubric (judge): style grade of the output on the criteria of a rubric file (`rubric` option).

Rubric (`rubrics/*.yaml`): `scale` ([1, 5] at most: a short scale is more reliable), `criteria`,
each with an `id`, a `weight`, a `definition` and either:
- `anchors`: concrete descriptions of the low, middle and high scores (e.g. 1, 3, 5); the judge
  gives the score, after a justification citing the output;
- `checks`: yes/no questions (`question`, `expected`: yes | no), more reliable than a score for
  what can be checked ("Are there remaining hesitations of the spoken language?"); the score of
  the criterion is computed from the share of checks passed (lowest = none, highest = all).

Judgment (one call, stored and reused while the rubric file is unchanged):
`criteria`: [{criterion, justification, score}] for the anchored criteria, `checks`: [{id, answer,
evidence}]. The prompt warns against the usual biases of LLM judges: scores clustered on 4
(use the whole scale, the top score only when the anchor is fully met) and the length bias (a
longer, more detailed text does not deserve a better score). The step input (the transcript) is
given so that the judge can recognize the speaker's voice (`with_source: false` to omit it).

Value = weighted mean of the criterion scores (rubric scale). Details: one score per criterion,
the failed checks, and `length_ratio` (words of the output / words of the input): the review app
warns when the grades follow the length of the outputs, or cluster on one value.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

from bench import steps
from bench.metrics import MetricResult
from bench.metrics.text import count_words

JUDGE = True
VERSION = 1
JUDGE_OPTIONS = {"rubric", "with_source"}
HIGHER_IS_BETTER = True
REPORT_DETAILS: dict[str, Optional[bool]] = {"length_ratio": None}
PERCENT = False
PERCENT_DETAILS: set[str] = set()
DIGITS = 2
NEEDS_REFERENCE = False

BENCH_DIR = Path(__file__).resolve().parents[1]
MAX_SCALE_STEPS = 4  # 1 to 5 at most

PROMPT = """You grade the style of the edited version of a Jewish studies lesson given orally in French,
with the rubric below. Content accuracy and coverage are measured elsewhere: only judge the criteria.

Rules (LLM judges are known to be too generous and to give 4 to everything):
- Use the whole scale {low}–{high}. The anchors say exactly what the scores mean; a score between
  two anchors means between the two descriptions. Give {high} only when the {high} anchor fully
  describes the text. A text with real flaws, even minor ones, does not get {high}.
- Length is not quality: a longer or more detailed text does NOT deserve a better score. Judge each
  criterion only on its definition; a short text that meets the definition gets the same score as
  a long one.
- For each criterion, write the justification FIRST (in French, one or two sentences, citing a
  precise passage or observation of the edited version), then the score that follows from it.
- Checklist: answer each question by yes or no, strictly; `evidence`: a short excerpt of the edited
  version that justifies the answer when something is found, else null.
{source_note}
Criteria to score:
{criteria}
{checks}
{source}Edited version:
{output}
"""

SOURCE_NOTE = "- The transcript of the lesson is given to recognize the speaker's way of teaching and what\n  is oral; do not grade the transcript.\n"


class CriterionScore(BaseModel):
    criterion: str = Field(description="Id of the criterion.")
    justification: str = Field(description="One or two sentences in French citing the edited version.")
    score: int


class CheckAnswer(BaseModel):
    id: str = Field(description="Id of the check.")
    answer: Literal["yes", "no"]
    evidence: Optional[str] = Field(description="Short excerpt of the edited version, or null.")


class RubricJudgment(BaseModel):
    criteria: list[CriterionScore]
    checks: list[CheckAnswer]


# --------------------------------------------------------------------------- #
# Rubric
# --------------------------------------------------------------------------- #

def _path(rubric: str) -> Path:
    path = Path(rubric)
    return path if path.is_absolute() else BENCH_DIR / path


@lru_cache(maxsize=16)
def _load(path: str, mtime: float) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_rubric(rubric: str) -> dict:
    path = _path(rubric)
    return _load(str(path), path.stat().st_mtime)


def rubric_problems(data: dict) -> list[str]:
    problems = []
    scale = data.get("scale", [1, 5])
    if not (isinstance(scale, list) and len(scale) == 2 and all(isinstance(s, int) for s in scale)
            and 0 < scale[1] - scale[0] <= MAX_SCALE_STEPS):
        problems.append(f"'scale' must be [low, high] with at most {MAX_SCALE_STEPS + 1} values, got {scale!r}")
        scale = [1, 5]
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return problems + ["'criteria' must be a non-empty list"]
    seen = set()
    for index, criterion in enumerate(criteria, 1):
        cid = criterion.get("id") if isinstance(criterion, dict) else None
        where = f"criterion {cid or index}"
        if not cid or not isinstance(cid, str):
            problems.append(f"{where}: 'id' is required")
            continue
        if cid in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(cid)
        if not isinstance(criterion.get("weight", 1), (int, float)) or criterion.get("weight", 1) <= 0:
            problems.append(f"{where}: 'weight' must be a positive number")
        if not criterion.get("definition"):
            problems.append(f"{where}: 'definition' is required")
        anchors, checks = criterion.get("anchors"), criterion.get("checks")
        if bool(anchors) == bool(checks):
            problems.append(f"{where}: give either 'anchors' (scored by the judge) or 'checks' (yes/no questions)")
        if anchors:
            if not isinstance(anchors, dict) or any(not isinstance(k, int) or not scale[0] <= k <= scale[1] for k in anchors):
                problems.append(f"{where}: anchors must be scores of the scale {scale}")
            elif scale[0] not in anchors or scale[1] not in anchors:
                problems.append(f"{where}: anchors must describe at least the lowest and the highest score")
        if checks:
            if not isinstance(checks, list) or not all(
                    isinstance(c, dict) and c.get("question") and _expected(c) in ("yes", "no") for c in checks):
                problems.append(f"{where}: each check needs a 'question' and 'expected: yes|no'")
    return problems


def check_options(options: dict) -> list[str]:
    rubric = options.get("rubric")
    if not rubric:
        return ["'rubric' is required (e.g. rubrics/edition_style.yaml)"]
    if not _path(str(rubric)).is_file():
        return [f"rubric file not found: {rubric}"]
    try:
        data = load_rubric(str(rubric))
    except yaml.YAMLError as error:
        return [f"{rubric}: invalid YAML ({error})"]
    problems = [f"{rubric}: {p}" for p in rubric_problems(data)]
    if not isinstance(options.get("with_source", True), bool):
        problems.append("'with_source' must be true or false")
    return problems


def _criteria(options: dict) -> list[dict]:
    return load_rubric(str(options["rubric"]))["criteria"]


def _scale(options: dict) -> tuple[int, int]:
    low, high = load_rubric(str(options["rubric"])).get("scale", [1, 5])
    return int(low), int(high)


def _expected(check: dict) -> Optional[str]:
    """`expected: no` unquoted is the YAML boolean false."""
    value = check.get("expected")
    return {True: "yes", False: "no"}.get(value, value) if isinstance(value, (bool, str)) else None


def _check_ids(criterion: dict) -> list[tuple[str, dict]]:
    return [(f"{criterion['id']}.{n}", check) for n, check in enumerate(criterion.get("checks") or [], 1)]


def report_details(options: dict) -> dict[str, Optional[bool]]:
    """One column per criterion (rubric dependent), then the length ratio (length bias)."""
    try:
        ids = [c["id"] for c in _criteria(options)]
    except (OSError, KeyError, TypeError):
        ids = []
    return {**{cid: True for cid in ids}, **REPORT_DETAILS}


def judge_inputs(item, options: Optional[dict] = None) -> Optional[str]:
    """The judgment depends on the rubric content, not only on its path."""
    rubric = (options or {}).get("rubric")
    if not rubric or not _path(str(rubric)).is_file():
        return None
    return hashlib.sha256(_path(str(rubric)).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Judge
# --------------------------------------------------------------------------- #

def _prompt_parts(options: dict) -> tuple[str, str]:
    criteria_lines, check_lines = [], []
    for criterion in _criteria(options):
        if criterion.get("anchors"):
            criteria_lines.append(f"- {criterion['id']}: {criterion['definition']}")
            for score, text in sorted(criterion["anchors"].items()):
                criteria_lines.append(f"    {score} = {text}")
        for check_id, check in _check_ids(criterion):
            check_lines.append(f"- {check_id}: {check['question']}")
    checks = ("Checklist:\n" + "\n".join(check_lines) + "\n") if check_lines else "Checklist: none (empty list).\n"
    return "\n".join(criteria_lines) or "(none: empty list)", checks


def _prompt(output: str, input_text: str, options: dict) -> str:
    low, high = _scale(options)
    criteria, checks = _prompt_parts(options)
    with_source = options.get("with_source", True) and input_text
    return PROMPT.format(
        low=low, high=high, criteria=criteria, checks=checks, output=output,
        source_note=SOURCE_NOTE if with_source else "",
        source=f"Transcript of the lesson:\n{input_text}\n\n" if with_source else "",
    )


def estimate_tokens(output: str, *, input_text: str, item, options: dict) -> tuple[int, int]:
    criteria = _criteria(options)
    checks = sum(len(c.get("checks") or []) for c in criteria)
    return steps.approx_tokens(_prompt(output, input_text, options)), 120 * len(criteria) + 40 * checks + 50


def judge(output: str, *, input_text: str, item=None, options: Optional[dict] = None, judge=None) -> dict:
    options = options or {}
    parsed = judge.ask(RubricJudgment, _prompt(output, input_text, options))
    return parsed.model_dump()


def compute(output: str, *, input_text: str, reference: Optional[str] = None, options: Optional[dict] = None,
            item=None, judge=None) -> MetricResult:
    """judge + score (one call)."""
    judgment = globals()["judge"](output, input_text=input_text, item=item, options=options, judge=judge)
    return score(judgment, output, input_text=input_text, item=item, options=options)


# --------------------------------------------------------------------------- #
# Score (no call)
# --------------------------------------------------------------------------- #

def score(judgment: dict, output: str, *, input_text: str, item=None, options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    low, high = _scale(options)
    rubric = load_rubric(str(options["rubric"]))
    scores = {c["criterion"]: c for c in judgment.get("criteria", [])}
    answers = {a["id"]: a for a in judgment.get("checks", [])}

    details: dict = {}
    rows, failed_checks, missing = [], [], []
    weighted = total_weight = 0.0
    for criterion in rubric["criteria"]:
        cid, weight = criterion["id"], float(criterion.get("weight", 1))
        row = {"criterion": cid, "weight": weight, "definition": criterion["definition"]}
        if criterion.get("checks"):
            checks = []
            for check_id, check in _check_ids(criterion):
                answer = answers.get(check_id)
                passed = None if answer is None else answer["answer"] == _expected(check)
                checks.append({"id": check_id, "question": check["question"], "expected": _expected(check),
                               "answer": answer["answer"] if answer else None,
                               "evidence": answer.get("evidence") if answer else None, "passed": passed})
                if passed is False:
                    failed_checks.append(check["question"])
            answered = [c for c in checks if c["passed"] is not None]
            value = low + (high - low) * sum(c["passed"] for c in answered) / len(answered) if answered else None
            row.update(source="checks", score=value, checks=checks)
        else:
            given = scores.get(cid)
            value = None if given is None else float(min(high, max(low, given["score"])))
            row.update(source="judge", score=value, judge_score=given["score"] if given else None,
                       justification=given["justification"] if given else None)
        if value is None:
            missing.append(cid)
        else:
            weighted += weight * value
            total_weight += weight
        details[cid] = value
        rows.append(row)

    words_output, words_input = count_words(output), count_words(input_text or "")
    details.update({
        "length_ratio": words_output / words_input if words_input else None,
        "words": words_output,
        "criteria": rows,
        "failed_checks": failed_checks,
        "missing_criteria": missing,
        "scale": [low, high],
        "rubric": rubric.get("name") or str(options["rubric"]),
        "rubric_version": rubric.get("version"),
    })
    return MetricResult(weighted / total_weight if total_weight else None, details)
