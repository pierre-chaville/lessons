"""LLM-judge metrics: judge model, evidence check, planning, cost estimate and execution.

A judge metric module (see metrics/__init__.py) sets `JUDGE = True`, a `VERSION`, the option keys
that change the judgment (`JUDGE_OPTIONS`) and exposes:

    def estimate_tokens(output, *, input_text, item, options) -> (tokens_in, tokens_out)
    def judge(output, *, input_text, item, options, judge: JudgeCalls) -> dict   # LLM calls: the findings
    def score(judgment, output, *, input_text, item, options) -> MetricResult    # no call: the policy

The judgment (raw findings of the judge) is stored in the score details and reused while the
generation, the metric version, the judge options and the judge (model, provider, params) are the
same (`judge_signature`). Scoring is re-done at every scoring phase from the stored judgment, so a
change of the scoring options (e.g. the faithfulness policy) costs no judge call. The cost of the
judge calls is stored in the score details (judge_tokens_*, judge_cost_usd).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

from rapidfuzz import fuzz

from bench import steps
from bench.db import BenchDB, options_json
from bench.metrics import get_metric_module

DEFAULT_EVIDENCE_THRESHOLD = 85
RETRY_DELAY_S = 2
JSON_SCHEMA_PROVIDERS = {"openai", "openrouter"}

# Raised by langchain_openai for every json_schema call, although nothing is streamed.
warnings.filterwarnings("ignore", message="Streaming with Pydantic response_format not yet supported")


# --------------------------------------------------------------------------- #
# Evidence check
# --------------------------------------------------------------------------- #

_QUOTE_CHARS = str.maketrans({"’": "'", "‘": "'", "´": "'", "׳": "'", "«": '"', "»": '"', "“": '"', "”": '"',
                               "״": '"', "־": " "})  # Hebrew geresh, gershayim, maqaf


def normalize_for_quotes(text: str) -> str:
    """Lowercase, accents, Hebrew vowel points / cantillation (combining marks) and markdown
    removed, quotes unified, spaces collapsed: the judge may copy a quote without them."""
    text = unicodedata.normalize("NFD", text.translate(_QUOTE_CHARS).lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[*_#>`\[\]]", " ", text)
    return " ".join(text.split())


def quote_found(quote: str, normalized_text: str, threshold: float = DEFAULT_EVIDENCE_THRESHOLD) -> bool:
    """True if `quote` (copied by the judge) is found, possibly with small differences, in the text
    (already normalized with normalize_for_quotes)."""
    quote = normalize_for_quotes(quote or "")
    if len(quote) < 8:
        return False
    if quote in normalized_text:
        return True
    return fuzz.partial_ratio(quote, normalized_text) >= threshold


_MARKDOWN_CHARS = set("*_#>`[]")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\(\.\.\.\))\s*")


class QuoteIndex:
    """A text normalized like normalize_for_quotes, with the position in the original text of
    every normalized character, to locate quotes in the original text."""

    def __init__(self, text: str):
        self.text = text
        chars: list[str] = []
        positions: list[int] = []
        for index, char in enumerate(text):
            for c in unicodedata.normalize("NFD", char.translate(_QUOTE_CHARS).lower()):
                if unicodedata.category(c) == "Mn":
                    continue
                if c.isspace() or c in _MARKDOWN_CHARS:
                    if chars and chars[-1] != " ":
                        chars.append(" ")
                        positions.append(index)
                    continue
                chars.append(c)
                positions.append(index)
        self.normalized = "".join(chars)
        self.positions = positions

    def locate(self, quote: Optional[str], threshold: float = DEFAULT_EVIDENCE_THRESHOLD) -> Optional[dict]:
        """{"start", "end", "score"} of `quote` in the original text, None if not found. Quotes
        shortened with "..." are located piece by piece (the longest piece must be found)."""
        pieces = [normalize_for_quotes(p) for p in _ELLIPSIS_RE.split(quote or "")]
        pieces = [p for p in pieces if len(p) >= 8]
        if not pieces or not self.normalized:
            return None
        found = []
        for piece in pieces:
            exact = self.normalized.find(piece)
            if exact >= 0:
                found.append((piece, 100.0, exact, exact + len(piece)))
                continue
            alignment = fuzz.partial_ratio_alignment(piece, self.normalized, score_cutoff=threshold)
            if alignment is not None:
                found.append((piece, alignment.score, alignment.dest_start, alignment.dest_end))
        longest = max(pieces, key=len)
        if not any(piece == longest for piece, *_ in found):
            return None
        start = min(f[2] for f in found)
        end = max(f[3] for f in found)
        return {
            "start": self.positions[start],
            "end": self.positions[max(start, end - 1)] + 1,
            "score": round(min(f[1] for f in found), 1),
        }


# --------------------------------------------------------------------------- #
# Judge model
# --------------------------------------------------------------------------- #


@dataclass
class JudgeModel:
    model_id: str
    provider: str
    params: dict
    timeout: float
    max_retries: int
    price: Optional[tuple[float, float]]  # None: no price in pricing.yaml
    flex: bool = False

    @classmethod
    def from_config(cls, config: dict, pricing: Any, flex: bool = False, timeout: float = 300,
                    max_retries: int = 2) -> "JudgeModel":
        judge = config.get("judge") or {}
        model_id, provider = judge.get("model"), str(judge.get("provider", "")).lower()
        use_flex = flex and pricing.flex_available(model_id, provider)
        return cls(
            model_id=model_id,
            provider=provider,
            params=dict(judge.get("params") or {}),
            timeout=float(judge.get("timeout_s", timeout)),
            max_retries=int(judge.get("max_retries", max_retries)),
            price=pricing.price(model_id, provider, flex=use_flex),
            flex=use_flex,
        )

    def cost(self, tokens_in: int, tokens_out: int) -> Optional[float]:
        if self.price is None:
            return None
        return (tokens_in * self.price[0] + tokens_out * self.price[1]) / 1_000_000

    def signature(self, metric: str, version: Any, options: dict, inputs: Any = None) -> str:
        """Identifies a judgment: same signature = same judgment (flex excluded). `inputs`: dataset
        data the judgment depends on besides the output (e.g. the ideas of idea_coverage)."""
        payload = {"metric": metric, "version": version, "model": self.model_id, "provider": self.provider,
                   "params": self.params, "options": options}
        if inputs is not None:
            payload["inputs"] = inputs
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class JudgeCalls:
    """The judge as seen by a metric: `ask(schema, prompt)`, tokens counted (failed calls included)."""

    def __init__(self, model: JudgeModel):
        self.model = model
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def ask(self, schema, prompt: str):
        params = {**self.model.params, **({"use_flex": True} if self.model.flex else {})}
        if self.model.provider in JSON_SCHEMA_PROVIDERS:
            # response_format instead of function tools: OpenAI reasoning models refuse function
            # tools in chat completions (reasoning_effort is on by default for some of them).
            params.setdefault("structured_output_method", "json_schema")
        for attempt in range(self.model.max_retries + 1):
            self.calls += 1
            try:
                parsed, tokens = steps.structured_call(schema, prompt, provider=self.model.provider,
                                                       model=self.model.model_id, params=params,
                                                       timeout=self.model.timeout)
            except Exception as exc:
                self.tokens_in += int(getattr(exc, "tokens_in", 0) or 0)
                self.tokens_out += int(getattr(exc, "tokens_out", 0) or 0)
                retryable = getattr(exc, "retryable", True) and getattr(exc, "status_code", None) not in (400, 401, 403, 404)
                if not retryable or attempt == self.model.max_retries:
                    raise
                time.sleep(RETRY_DELAY_S * 2**attempt)
                continue
            self.tokens_in += tokens["tokens_in"]
            self.tokens_out += tokens["tokens_out"]
            return parsed
        raise AssertionError("unreachable")


# --------------------------------------------------------------------------- #
# Planning and execution
# --------------------------------------------------------------------------- #


@dataclass
class JudgeTask:
    job: Any                 # run.Job
    metric: str
    options: dict
    module: Any
    signature: str
    output: Optional[str]    # None: generation not done yet (estimated from the reference)
    judgment: Optional[dict] = None  # stored judgment: re-scored without judge call
    stored: dict = field(default_factory=dict)  # judge_* details of the stored judgment
    est_tokens_in: int = 0
    est_tokens_out: int = 0


def is_judge_metric(name: str) -> bool:
    try:
        return bool(getattr(get_metric_module(name), "JUDGE", False))
    except KeyError:
        return False


def judge_options(module, options: dict) -> dict:
    """The options that change the judgment (the others only change the scoring)."""
    keys = getattr(module, "JUDGE_OPTIONS", set())
    return {k: v for k, v in options.items() if k in keys}


JUDGE_DETAILS = ("judge_signature", "judge_calls", "judge_tokens_in", "judge_tokens_out", "judge_cost_usd", "judge_flex")


def plan_judge(config: dict, jobs: list[Any], db: Optional[BenchDB], judge: JudgeModel,
               metric_specs, reference_text, gold_input, include_pending: bool = False) -> list[JudgeTask]:
    """One task per (successful generation, judge metric): `task.judgment` set when a judgment with
    the same signature is stored (whatever the scoring options), else a judge call is needed.
    `include_pending`: also the jobs not generated yet (for the estimate of a dry run)."""
    stored: dict[tuple[int, str, str], dict] = {}  # (generation, metric, signature) -> details
    if db is not None:
        for row in db.scores([j.cached_id for j in jobs if j.cached_id is not None]):
            details = json.loads(row["details"] or "{}")
            if details.get("judgment") is not None and details.get("judge_signature"):
                stored[(row["generation_id"], row["metric"], details["judge_signature"])] = details
    tasks = []
    for job in jobs:
        if job.cached_id is None and not include_pending:
            continue
        for name, options in metric_specs(config["steps"][job.step]):
            if not is_judge_metric(name):
                continue
            module = get_metric_module(name)
            inputs = module.judge_inputs(job.item) if hasattr(module, "judge_inputs") else None
            signature = judge.signature(name, getattr(module, "VERSION", 1), judge_options(module, options), inputs)
            output = db.generation(job.cached_id)["output"] if job.cached_id is not None and db is not None else None
            task = JudgeTask(job, name, options, module, signature, output)
            details = stored.get((job.cached_id, name, signature)) if job.cached_id is not None else None
            if details is not None:
                task.judgment = details["judgment"]
                task.stored = {k: details.get(k) for k in JUDGE_DETAILS}
            else:
                proxy = output if output is not None else (reference_text(job.task, job.item) or "")
                input_text = job.input_text if job.input_text is not None else gold_input(job.task, job.item)
                task.est_tokens_in, task.est_tokens_out = module.estimate_tokens(
                    proxy, input_text=input_text, item=job.item, options=options)
            tasks.append(task)
    return tasks


def calls_needed(tasks: list[JudgeTask]) -> list[JudgeTask]:
    return [t for t in tasks if t.judgment is None]


def print_judge_plan(tasks: list[JudgeTask], judge: JudgeModel) -> float:
    """Table of the judge scores to compute per step x metric. Returns the estimated cost."""
    tasks = calls_needed(tasks)
    if not tasks:
        return 0.0
    groups: dict[tuple[str, str], list[JudgeTask]] = {}
    for task in tasks:
        groups.setdefault((task.job.step, task.metric), []).append(task)
    label = f"{judge.model_id}{' (flex)' if judge.flex else ''}"
    print(f"\nJudge: {label}")
    header = f"{'step':12} {'metric':20} {'scores':>6} {'est. tokens in/out':>20} {'est. USD':>9}"
    print(header)
    print("-" * len(header))
    total, unknown, pending = 0.0, False, False
    for (step, metric), group in groups.items():
        tokens_in = sum(t.est_tokens_in for t in group)
        tokens_out = sum(t.est_tokens_out for t in group)
        cost = judge.cost(tokens_in, tokens_out)
        unknown |= cost is None
        total += cost or 0.0
        mark = ""
        if any(t.output is None for t in group):
            mark, pending = " *", True
        cost_text = "?" if cost is None else f"{cost:.4f}"
        print(f"{step:12} {metric:20} {len(group):>6} {f'{tokens_in:,}/{tokens_out:,}':>20} {cost_text:>9}{mark}")
    print("-" * len(header))
    print(f"{len(tasks)} judge scores -- estimated cost ${total:.4f}"
          + (" + unknown (no price for the judge in configs/pricing.yaml)" if unknown else ""))
    if pending:
        print("* output not generated yet: estimated from the reference (edited.md / summary.md)")
    print("Judge estimates do not include reasoning tokens (thinking judges cost more).")
    return total


@dataclass
class JudgeSummary:
    scores: int = 0
    rescored: int = 0
    failed: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    def print(self) -> None:
        if self.rescored:
            print(f"Judge: {self.rescored} scores re-computed from stored judgments (no call)")
        if self.scores or self.failed:
            print(f"Judge: {self.scores} scores, {self.failed} failed -- cost ${self.cost_usd:.4f}")
        for error in self.errors[:10]:
            print(f"  ERROR {error}")


def _score(task: JudgeTask, judgment: dict):
    return task.module.score(judgment, task.output, input_text=task.job.input_text, item=task.job.item,
                             options=task.options)


def _judge(task: JudgeTask, judge: JudgeModel) -> tuple[Optional[dict], JudgeCalls, Optional[str]]:
    calls = JudgeCalls(judge)
    try:
        judgment = task.module.judge(task.output, input_text=task.job.input_text, item=task.job.item,
                                     options=task.options, judge=calls)
        return judgment, calls, None
    except Exception as exc:
        return None, calls, f"{type(exc).__name__}: {exc}"


def _store(db: BenchDB, task: JudgeTask, judgment: dict, judge_details: dict, judge_model: str) -> Any:
    result = _score(task, judgment)
    details = {**result.details, **judge_details, "judgment": judgment}
    db.upsert_score(task.job.cached_id, task.metric, task.options, result.value, details, judge_model=judge_model)
    return result


def rescore_judged(tasks: list[JudgeTask], db: BenchDB, judge: JudgeModel, summary: JudgeSummary) -> None:
    """Score again the stored judgments with the current options and code (cheap, no call)."""
    for task in tasks:
        if task.judgment is None or task.output is None:
            continue
        try:
            _store(db, task, task.judgment, task.stored, judge.model_id)
            summary.rescored += 1
        except Exception as exc:
            summary.errors.append(f"{task.metric} | {task.job.label()}: re-scoring failed: {type(exc).__name__}: {exc}")
    db.commit()


def run_judge(tasks: list[JudgeTask], db: BenchDB, judge: JudgeModel, workers: int = 1,
              max_usd: Optional[float] = None, summary: Optional[JudgeSummary] = None) -> JudgeSummary:
    """Judge calls (in parallel threads) for the tasks without stored judgment; stored in the main thread."""
    summary = summary or JudgeSummary()
    tasks = [t for t in calls_needed(tasks) if t.output is not None]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {}
        pending = list(tasks)
        while pending or futures:
            while pending and len(futures) < max(1, workers):
                if max_usd is not None and summary.cost_usd >= max_usd:
                    summary.errors.append(f"budget: ${summary.cost_usd:.4f} spent, {len(pending)} judge scores not computed")
                    pending = []
                    break
                task = pending.pop(0)
                futures[pool.submit(_judge, task, judge)] = task
            if not futures:
                break
            done = next(as_completed(futures))
            task = futures.pop(done)
            judgment, calls, error = done.result()
            cost = judge.cost(calls.tokens_in, calls.tokens_out) or 0.0
            summary.cost_usd += cost
            label = task.job.label()
            if error is None:
                try:
                    result = _store(db, task, judgment, {
                        "judge_signature": task.signature, "judge_calls": calls.calls,
                        "judge_tokens_in": calls.tokens_in, "judge_tokens_out": calls.tokens_out,
                        "judge_cost_usd": round(cost, 6), "judge_flex": judge.flex,
                    }, judge.model_id)
                    db.commit()
                except Exception as exc:
                    error = f"scoring failed: {type(exc).__name__}: {exc}"
            if error:
                summary.failed += 1
                summary.errors.append(f"{task.metric} | {label}: {error}")
                print(f"  judge FAILED {task.metric:16} {label}  {error}")
                continue
            summary.scores += 1
            value = "–" if result.value is None else f"{result.value:.3f}"
            print(f"  judge ok     {task.metric:16} {label}  {value}  ${cost:.4f}")
    return summary

