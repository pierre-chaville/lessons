"""LLM-judge metrics: judge model, evidence check, planning, cost estimate and execution.

A judge metric module (see metrics/__init__.py) sets `JUDGE = True`, a `VERSION` and exposes:

    def estimate_tokens(output, *, input_text, item, options) -> (tokens_in, tokens_out)
    def compute(output, *, input_text, reference, options, item, judge: JudgeCalls) -> MetricResult

Judge scores are expensive, so they are cached: a score is reused while the generation, the metric
version, its options and the judge (model, provider, params) are the same (`judge_signature` in the
score details). The cost of the judge calls is stored in the score details (tokens, cost_usd).
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

_QUOTE_CHARS = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "«": '"', "»": '"', "“": '"', "”": '"'})


def normalize_for_quotes(text: str) -> str:
    """Lowercase, accents and markdown removed, quotes unified, spaces collapsed."""
    text = unicodedata.normalize("NFD", text.translate(_QUOTE_CHARS).lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[*_#>\[\]]", " ", text)
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

    def signature(self, metric: str, version: Any, options: dict) -> str:
        """Identifies a judge score: same signature = same judgment (flex excluded)."""
        payload = {"metric": metric, "version": version, "model": self.model_id, "provider": self.provider,
                   "params": self.params, "options": options}
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
    est_tokens_in: int = 0
    est_tokens_out: int = 0


def is_judge_metric(name: str) -> bool:
    try:
        return bool(getattr(get_metric_module(name), "JUDGE", False))
    except KeyError:
        return False


def plan_judge(config: dict, jobs: list[Any], db: Optional[BenchDB], judge: JudgeModel,
               metric_specs, reference_text, gold_input, include_pending: bool = False) -> list[JudgeTask]:
    """Judge scores to compute: one per (successful generation, judge metric) not cached yet.
    `include_pending`: also the jobs not generated yet (for the estimate of a dry run)."""
    cached_scores: dict[tuple[int, str, str], str] = {}
    if db is not None:
        ids = [j.cached_id for j in jobs if j.cached_id is not None]
        for row in db.scores(ids):
            details = json.loads(row["details"] or "{}")
            cached_scores[(row["generation_id"], row["metric"], row["options"])] = details.get("judge_signature")
    tasks = []
    for job in jobs:
        if job.cached_id is None and not include_pending:
            continue
        for name, options in metric_specs(config["steps"][job.step]):
            if not is_judge_metric(name):
                continue
            module = get_metric_module(name)
            signature = judge.signature(name, getattr(module, "VERSION", 1), options)
            if job.cached_id is not None:
                if cached_scores.get((job.cached_id, name, options_json(options))) == signature:
                    continue
                output = db.generation(job.cached_id)["output"] if db is not None else None
            else:
                output = None
            task = JudgeTask(job, name, options, module, signature, output)
            proxy = output if output is not None else (reference_text(job.task, job.item) or "")
            input_text = job.input_text if job.input_text is not None else gold_input(job.task, job.item)
            task.est_tokens_in, task.est_tokens_out = module.estimate_tokens(
                proxy, input_text=input_text, item=job.item, options=options)
            tasks.append(task)
    return tasks


def print_judge_plan(tasks: list[JudgeTask], judge: JudgeModel) -> float:
    """Table of the judge scores to compute per step x metric. Returns the estimated cost."""
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
    failed: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    def print(self) -> None:
        if self.scores or self.failed:
            print(f"Judge: {self.scores} scores, {self.failed} failed -- cost ${self.cost_usd:.4f}")
        for error in self.errors[:10]:
            print(f"  ERROR {error}")


def _compute(task: JudgeTask, judge: JudgeModel, reference_text) -> tuple[Any, JudgeCalls, Optional[str]]:
    calls = JudgeCalls(judge)
    try:
        result = task.module.compute(
            task.output, input_text=task.job.input_text, reference=reference_text(task.job.task, task.job.item),
            options=task.options, item=task.job.item, judge=calls,
        )
        return result, calls, None
    except Exception as exc:
        return None, calls, f"{type(exc).__name__}: {exc}"


def run_judge(tasks: list[JudgeTask], db: BenchDB, judge: JudgeModel, reference_text, workers: int = 1,
              max_usd: Optional[float] = None) -> JudgeSummary:
    """Compute the judge scores (in parallel threads) and store them (main thread)."""
    summary = JudgeSummary()
    tasks = [t for t in tasks if t.output is not None]
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
                futures[pool.submit(_compute, task, judge, reference_text)] = task
            if not futures:
                break
            done = next(as_completed(futures))
            task = futures.pop(done)
            result, calls, error = done.result()
            cost = judge.cost(calls.tokens_in, calls.tokens_out) or 0.0
            summary.cost_usd += cost
            label = f"{task.job.step} | {task.job.item.id} | {task.job.model_alias} | {task.job.prompt_name} | r{task.job.repeat}"
            if error:
                summary.failed += 1
                summary.errors.append(f"{task.metric} | {label}: {error}")
                print(f"  judge FAILED {task.metric:16} {label}  {error}")
                continue
            details = dict(result.details)
            details.update({
                "judge_signature": task.signature, "judge_calls": calls.calls,
                "judge_tokens_in": calls.tokens_in, "judge_tokens_out": calls.tokens_out,
                "judge_cost_usd": round(cost, 6), "judge_flex": judge.flex,
            })
            db.upsert_score(task.job.cached_id, task.metric, task.options, result.value, details,
                            judge_model=judge.model_id)
            db.commit()
            summary.scores += 1
            value = "–" if result.value is None else f"{result.value:.3f}"
            print(f"  judge ok     {task.metric:16} {label}  {value}  ${cost:.4f}")
    return summary
