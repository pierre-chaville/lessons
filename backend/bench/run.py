"""Bench runner: validation, generation (with cache, cost estimate and budget), scoring.
Results are browsed with the review app (python -m bench.review_app).

Usage (from backend/):
    python -m bench.run bench/configs/<campaign>.yaml --check       # validate config + dataset
    python -m bench.run bench/configs/<campaign>.yaml --dry-run     # calls to run + estimated cost
    python -m bench.run bench/configs/<campaign>.yaml [--limit N] [--steps ...] [--models ...]
    python -m bench.run bench/configs/<campaign>.yaml --only score  # or: --only generate
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from bench.dataset import BENCH_DIR, TASK_DATASET, Issue, LessonItem, describe, format_transcript, load_dataset
from bench.db import BenchDB
from bench.judge import (JudgeModel, JudgeSummary, calls_needed, is_judge_metric, plan_judge, print_judge_plan,
                         rescore_judged, run_judge)
from bench.metrics import get_metric_module
from bench.score import metric_specs, reference_text, score_jobs
from bench.steps import PROVIDERS

INPUT_SOURCES = ("raw", "gold", "pipeline")
PRICING_PATH = BENCH_DIR / "configs" / "pricing.yaml"
DEFAULTS = {"repeats": 1, "timeout_s": 180, "max_retries": 2, "input_source": "gold", "workers": 1}
RETRY_DELAY_S = 2

logger = logging.getLogger("bench")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    return config


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_price(price: Any) -> Optional[tuple[float, float]]:
    """`[in, out]` or `{input_per_mtok, output_per_mtok}` -> (in, out) in USD per million tokens."""
    if isinstance(price, dict):
        price = (price.get("input_per_mtok"), price.get("output_per_mtok"))
    if not isinstance(price, (list, tuple)) or len(price) != 2:
        return None
    try:
        values = float(price[0]), float(price[1])
    except (TypeError, ValueError):
        return None
    return values if min(values) >= 0 else None


def compute_cost(price: tuple[float, float], tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


@dataclass
class Pricing:
    """Prices of configs/pricing.yaml, shared by all campaigns: a list of
    `{id, price: [input, output], provider (optional), flex (optional)}` in USD per million tokens;
    `flex` = ratio of the flex price to the standard price (e.g. 0.5), when the model has a flex tier."""

    path: Path
    prices: dict[tuple[str, Optional[str]], tuple[float, float]]
    issues: list[Issue]
    flex_ratios: dict[tuple[str, Optional[str]], float] = field(default_factory=dict)

    def _key(self, table: dict, model_id: str, provider: Optional[str]) -> Optional[tuple]:
        """Entry with this id and provider, else the entry with this id and no provider."""
        key = (model_id, str(provider).lower() if provider else None)
        if key in table:
            return key
        return (model_id, None) if (model_id, None) in table else None

    def flex_ratio(self, model_id: str, provider: Optional[str]) -> Optional[float]:
        key = self._key(self.prices, model_id, provider)
        return self.flex_ratios.get(key) if key else None

    def flex_available(self, model_id: str, provider: Optional[str]) -> bool:
        """Flex calls go through OpenRouter (service_tier "flex"), for models with a flex ratio."""
        return str(provider or "").lower() == "openrouter" and self.flex_ratio(model_id, provider) is not None

    def price(self, model_id: str, provider: Optional[str], flex: bool = False) -> Optional[tuple[float, float]]:
        """Standard price, or flex price (standard x flex ratio) when `flex` and the model has one."""
        key = self._key(self.prices, model_id, provider)
        if key is None:
            return None
        price = self.prices[key]
        ratio = self.flex_ratios.get(key) if flex else None
        return (price[0] * ratio, price[1] * ratio) if ratio else price


def load_pricing(path: Path = PRICING_PATH) -> Pricing:
    pricing = Pricing(path, {}, [])
    name = path.relative_to(BENCH_DIR).as_posix() if path.is_relative_to(BENCH_DIR) else str(path)
    if not path.is_file():
        pricing.issues.append(Issue("error", f"pricing file not found: {name}"))
        return pricing
    with path.open(encoding="utf-8-sig") as f:
        entries = yaml.safe_load(f) or []
    if not isinstance(entries, list):
        pricing.issues.append(Issue("error", f"{name}: expected a list of {{id, price}}"))
        return pricing
    for index, entry in enumerate(entries, start=1):
        model_id = entry.get("id") if isinstance(entry, dict) else None
        price = parse_price(entry.get("price")) if isinstance(entry, dict) else None
        if not isinstance(model_id, str) or price is None:
            pricing.issues.append(Issue(
                "error", f"{name}: entry {index}: expected {{id, price: [input, output]}}, got {entry!r}"
            ))
            continue
        provider = entry.get("provider")
        key = (model_id, str(provider).lower() if provider else None)
        if key in pricing.prices:
            pricing.issues.append(Issue("error", f"{name}: duplicate price for {model_id!r}"
                                                 f"{f' ({provider})' if provider else ''}"))
        pricing.prices[key] = price
        flex = entry.get("flex")
        if flex is not None:
            if isinstance(flex, bool) or not isinstance(flex, (int, float)) or not 0 < flex <= 1:
                pricing.issues.append(Issue("error", f"{name}: {model_id!r}: flex must be a ratio in ]0, 1], got {flex!r}"))
            else:
                pricing.flex_ratios[key] = float(flex)
    return pricing


def setting(config: dict, step: dict, key: str) -> Any:
    """Step value, else campaign default, else built-in default."""
    if key in step:
        return step[key]
    return (config.get("defaults") or {}).get(key, DEFAULTS[key])


def step_task(name: str, step: dict) -> str:
    return step.get("task", name)


def function_spec(name: str, step: dict) -> str:
    return step.get("function") or f"steps.{step_task(name, step)}"


def resolve_function(spec: str) -> Callable:
    """`steps.correction` -> bench.steps.correction; other dotted paths are imported as is."""
    module_name, _, attr = spec.rpartition(".")
    if not module_name:
        raise ValueError(f"{spec!r} is not a dotted path (module.function)")
    candidates = [module_name] if module_name.startswith("bench.") else [f"bench.{module_name}", module_name]
    for candidate in candidates:
        try:
            module = importlib.import_module(candidate)
        except ModuleNotFoundError as exc:
            if exc.name and (candidate == exc.name or candidate.startswith(exc.name + ".")):
                continue  # this candidate does not exist, try the next one
            raise
        func = getattr(module, attr, None)
        if not callable(func):
            raise ValueError(f"no function {attr!r} in {candidate}")
        return func
    raise ValueError(f"module {module_name!r} not found")


def step_version(step: dict, func: Callable) -> str:
    if "version" in step:
        return str(step["version"])
    versions = getattr(sys.modules[func.__module__], "VERSIONS", {})
    return str(versions.get(func.__name__, 1))


def previous_step(config: dict, name: str) -> Optional[str]:
    """Input step of a `pipeline` step: `from_step`, else the previous step of the campaign."""
    steps = config.get("steps") or {}
    if steps.get(name, {}).get("from_step"):
        return steps[name]["from_step"]
    names = list(steps)
    index = names.index(name)
    return names[index - 1] if index > 0 else None


def validate_config(config: dict, items: list[LessonItem], selected: Optional[list[str]] = None) -> list[Issue]:
    """Config errors that would make a run fail or be wrong. `selected`: only check these steps."""
    issues: list[Issue] = []

    def error(message: str) -> None:
        issues.append(Issue("error", message))

    def warn(message: str) -> None:
        issues.append(Issue("warning", message))

    def check_route(prefix: str, model_id: Any, provider: Any, report: Callable[[str], None] = error) -> None:
        if not isinstance(model_id, str) or not model_id.strip():
            report(f"{prefix}: model id must be a non-empty string, got {model_id!r}")
        if not isinstance(provider, str) or provider.lower() not in PROVIDERS:
            report(f"{prefix}: 'provider' must be one of {list(PROVIDERS)}, got {provider!r}")

    pricing = load_pricing()
    issues += pricing.issues
    used = {
        alias
        for name, step in (config.get("steps") or {}).items()
        if isinstance(step, dict) and (not selected or name in selected)
        for alias in step.get("models") or []
    }

    models = config.get("models")
    if not isinstance(models, dict) or not models:
        error("'models' must be a mapping alias -> {id, provider, params}")
        models = {}
    for alias, spec in models.items():
        if not isinstance(spec, dict):
            error(f"model {alias!r}: expected a mapping with id/provider/params")
            continue
        check_route(f"model {alias!r}", spec.get("id"), spec.get("provider"))
        if "price" in spec:
            warn(f"model {alias!r}: 'price' is ignored, prices are read from configs/pricing.yaml")
        if isinstance(spec.get("id"), str) and pricing.price(spec["id"], spec.get("provider")) is None:
            # Blocking only for the models that will be called.
            (error if alias in used else warn)(f"model {alias!r}: no price for {spec['id']!r} in configs/pricing.yaml")
        if not isinstance(spec.get("params") or {}, dict):
            error(f"model {alias!r}: 'params' must be a mapping")

    steps = config.get("steps")
    if not isinstance(steps, dict) or not steps:
        error("'steps' must be a non-empty mapping")
        steps = {}
    for name in selected or []:
        if name not in steps:
            error(f"unknown step {name!r} (defined: {', '.join(steps)})")

    for name, step in steps.items():
        if selected and name not in selected:
            continue
        prefix = f"step {name!r}"
        if not isinstance(step, dict):
            error(f"{prefix}: expected a mapping")
            continue

        task = step_task(name, step)
        kind = TASK_DATASET.get(task)
        if kind is None:
            error(f"{prefix}: unknown task {task!r} (known tasks: {', '.join(TASK_DATASET)})")
        elif not any(i.kind == kind for i in items):
            warn(f"{prefix} needs '{kind}' lessons but dataset.{kind} is empty")

        spec = function_spec(name, step)
        try:
            resolve_function(spec)
        except (ImportError, ValueError) as exc:
            error(f"{prefix}: function {spec!r} not available ({exc})")

        prompts = step.get("prompts")
        if not isinstance(prompts, list) or not prompts:
            error(f"{prefix}: 'prompts' must be a non-empty list")
        else:
            for prompt in prompts:
                if not (BENCH_DIR / str(prompt)).is_file():
                    error(f"{prefix}: prompt file not found: {prompt}")

        step_models = step.get("models")
        if not isinstance(step_models, list) or not step_models:
            error(f"{prefix}: 'models' must be a non-empty list of model aliases")
        else:
            for alias in step_models:
                if alias not in models:
                    error(f"{prefix}: unknown model alias {alias!r} (defined: {', '.join(models)})")

        source = setting(config, step, "input_source")
        if source not in INPUT_SOURCES:
            error(f"{prefix}: input_source must be one of {list(INPUT_SOURCES)}, got {source!r}")
        elif source == "pipeline":
            prev = previous_step(config, name)
            if prev is None or prev not in steps:
                error(f"{prefix}: input_source 'pipeline' needs a previous step (or a valid 'from_step')")

        repeats = setting(config, step, "repeats")
        if not isinstance(repeats, int) or repeats < 1:
            error(f"{prefix}: repeats must be an integer >= 1, got {repeats!r}")
        if not isinstance(step.get("params") or {}, dict):
            error(f"{prefix}: 'params' must be a mapping")

        for metric, options in metric_specs(step):
            try:
                check = getattr(get_metric_module(metric), "check_options", None)
            except KeyError:
                check = None
            for problem in check(options) if check else []:
                error(f"{prefix}: metric {metric}: {problem}")
            baseline = options.get("baseline")
            if baseline and baseline not in models:
                warn(f"{prefix}: metric {metric}: baseline {baseline!r} is not a model alias")
            rubric = options.get("rubric")
            if rubric and not (BENCH_DIR / str(rubric)).is_file():
                warn(f"{prefix}: metric {metric}: rubric file not found: {rubric}")

    max_usd = (config.get("budget") or {}).get("max_usd")
    if max_usd is None:
        warn("budget.max_usd is not set: no cost limit")
    elif not isinstance(max_usd, (int, float)) or max_usd <= 0:
        error(f"budget.max_usd must be a positive number, got {max_usd!r}")
    judge = config.get("judge") or {}
    uses_judge = any(
        metric.startswith("judge_") or is_judge_metric(metric)
        for name, step in steps.items()
        if isinstance(step, dict) and (not selected or name in selected)
        for metric, _ in metric_specs(step)
    )
    if judge or uses_judge:
        # Only blocking when a selected step has a judge metric.
        check_route("judge", judge.get("model"), judge.get("provider"), error if uses_judge else warn)
    calibration = judge.get("calibration_set")
    if calibration and not (BENCH_DIR / str(calibration)).is_file():
        warn(f"judge.calibration_set not found: {calibration}")
    return issues


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


def gold_input(task: str, item: LessonItem) -> str:
    """Input of a step in `gold` mode: the hand-made output of the previous step of the app.
    Summary: edited.md (the app summarizes the edited text)."""
    if task == "summary":
        return item.edited or ""
    return format_transcript(item.corrected or [])


@dataclass
class Job:
    """One call of a step adapter (lesson x model x prompt x repeat)."""

    step: str
    task: str
    function: str
    func: Callable
    version: str
    item: LessonItem
    model_alias: str
    provider: str
    model_id: str
    params: dict
    price: tuple[float, float]
    prompt_path: str
    prompt: str
    input_source: str
    repeat: int
    timeout: float
    max_retries: int
    input_text: Optional[str] = None  # None until resolved (pipeline input not generated yet)
    input_generation_id: Optional[int] = None
    est_tokens_in: int = 0
    est_tokens_out: int = 0
    cached_id: Optional[int] = None
    flex: bool = False  # OpenRouter flex tier (--flex); not part of the cache key

    @property
    def call_params(self) -> dict:
        """Params given to the adapter: the campaign params, plus use_flex in flex mode."""
        return {**self.params, "use_flex": True} if self.flex else dict(self.params)

    @property
    def est_cost(self) -> float:
        return compute_cost(self.price, self.est_tokens_in, self.est_tokens_out)

    @property
    def prompt_name(self) -> str:
        return Path(self.prompt_path).stem

    @property
    def cache_key(self) -> str:
        assert self.input_text is not None, "input not resolved"
        payload = {
            "lesson": self.item.id,
            "step": self.step,
            "function": self.function,
            "version": self.version,
            "provider": self.provider,
            "model": self.model_id,
            "params": self.params,
            "prompt": sha256(self.prompt),
            "input": sha256(self.input_text),
            "repeat": self.repeat,
        }
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))

    def label(self) -> str:
        return f"{self.step} | {self.item.id} | {self.model_alias} | {self.prompt_name} | r{self.repeat}"


class Planner:
    def __init__(self, config: dict, items: list[LessonItem], db: Optional[BenchDB], flex: bool = False):
        self.config = config
        self.items = items
        self.db = db
        self.flex = flex
        self.pricing = load_pricing()
        self._prompts: dict[str, str] = {}

    def prompt_text(self, path: str) -> str:
        if path not in self._prompts:
            self._prompts[path] = (BENCH_DIR / path).read_text(encoding="utf-8-sig")
        return self._prompts[path]

    def make_job(self, step_name: str, item: LessonItem, alias: str, prompt_path: str, repeat: int) -> Job:
        step = self.config["steps"][step_name]
        model = self.config["models"][alias]
        spec = function_spec(step_name, step)
        func = resolve_function(spec)
        flex = self.flex and self.pricing.flex_available(model["id"], model.get("provider"))
        return Job(
            step=step_name,
            task=step_task(step_name, step),
            function=spec,
            func=func,
            version=step_version(step, func),
            item=item,
            model_alias=alias,
            provider=str(model["provider"]).lower(),
            model_id=model["id"],
            params={**(model.get("params") or {}), **(step.get("params") or {})},
            price=self.pricing.price(model["id"], model.get("provider"), flex=flex),
            flex=flex,
            prompt_path=str(prompt_path),
            prompt=self.prompt_text(str(prompt_path)),
            input_source=setting(self.config, step, "input_source"),
            repeat=repeat,
            timeout=float(setting(self.config, step, "timeout_s")),
            max_retries=int(setting(self.config, step, "max_retries")),
        )

    def jobs_for_step(self, step_name: str, limit: Optional[int], models: Optional[list[str]]) -> tuple[list[Job], list[str]]:
        step = self.config["steps"][step_name]
        kind = TASK_DATASET[step_task(step_name, step)]
        lessons = [i for i in self.items if i.kind == kind][:limit]
        aliases = [a for a in step["models"] if not models or a in models]
        repeats = int(setting(self.config, step, "repeats"))
        jobs, skipped = [], []
        for item in lessons:
            if setting(self.config, step, "input_source") == "raw" and item.initial is None:
                skipped.append(f"{step_name} | {item.id}: no initial.md for input_source 'raw'")
                continue
            for prompt_path in step["prompts"]:
                for alias in aliases:
                    for repeat in range(repeats):
                        jobs.append(self.make_job(step_name, item, alias, prompt_path, repeat))
        return jobs, skipped

    def resolve_input(self, job: Job) -> bool:
        """Set job.input_text. False if it depends on a generation that does not exist yet."""
        if job.input_text is not None:
            return True
        if job.input_source == "raw":
            job.input_text = format_transcript(job.item.initial or [])
            return True
        if job.input_source == "gold":
            job.input_text = gold_input(job.task, job.item)
            return True
        # pipeline: output of the previous step, same lesson and model, first prompt, first repeat
        prev_name = previous_step(self.config, job.step)
        prev_prompt = self.config["steps"][prev_name]["prompts"][0]
        prev = self.make_job(prev_name, job.item, job.model_alias, prev_prompt, 0)
        if not self.resolve_input(prev) or self.db is None:
            return False
        row = self.db.cached(prev.cache_key)
        if row is None:
            return False
        job.input_text = row["output"]
        job.input_generation_id = row["id"]
        return True

    def estimate(self, job: Job) -> None:
        """Token estimate of one job. Unresolved pipeline inputs are approximated by the gold input."""
        text = job.input_text if job.input_text is not None else gold_input(job.task, job.item)
        module = sys.modules[job.func.__module__]
        estimator = getattr(module, f"estimate_{job.func.__name__}", None)
        if estimator is None:
            from bench.steps import estimate_tokens as estimator
        job.est_tokens_in, job.est_tokens_out = estimator(text, job.prompt, job.params)

    def plan(self, steps: list[str], limit: Optional[int], models: Optional[list[str]]) -> tuple[list[Job], list[str]]:
        all_jobs, all_skipped = [], []
        for step_name in steps:
            jobs, skipped = self.jobs_for_step(step_name, limit, models)
            all_skipped.extend(skipped)
            for job in jobs:
                if self.resolve_input(job) and self.db is not None:
                    row = self.db.cached(job.cache_key)
                    job.cached_id = row["id"] if row else None
                self.estimate(job)
            all_jobs.extend(jobs)
        return all_jobs, all_skipped


def print_flex(requested: bool, flex: dict[str, bool]) -> None:
    """--flex summary: {model label: flex available}."""
    if not requested:
        return
    on = sorted(m for m, available in flex.items() if available)
    off = sorted(m for m, available in flex.items() if not available)
    print(f"--flex: flex tier (price x ratio of configs/pricing.yaml) for {', '.join(on) or 'no model'}"
          + (f"; standard tier for {', '.join(off)} (not OpenRouter or no flex ratio)" if off else ""))
    if on:
        print("Flex calls can be slower and may be refused when capacity is short (retried as errors).")


def print_plan(jobs: list[Job], max_usd: Optional[float], flex: bool = False) -> float:
    """Table of the planned calls per step x model x prompt. Returns the estimated cost to run."""
    groups: dict[tuple, list[Job]] = {}
    for job in jobs:
        groups.setdefault((job.step, job.model_alias + (" (flex)" if job.flex else ""), job.prompt_name), []).append(job)

    w_step = max([len(k[0]) for k in groups] + [4])
    w_model = max([len(k[1]) for k in groups] + [5])
    w_prompt = max([len(k[2]) for k in groups] + [6])
    header = (f"{'step':{w_step}} {'model':{w_model}} {'prompt':{w_prompt}} {'lessons':>7} {'repeats':>7} "
              f"{'calls':>5} {'cached':>6} {'to run':>6} {'est. tokens in/out':>20} {'est. USD':>9}")
    print(header)
    print("-" * len(header))
    total = 0.0
    pending_pipeline = False
    for (step, alias, prompt), group in groups.items():
        todo = [j for j in group if j.cached_id is None]
        cost = sum(j.est_cost for j in todo)
        total += cost
        tokens = f"{sum(j.est_tokens_in for j in todo):,}/{sum(j.est_tokens_out for j in todo):,}"
        n_lessons, n_repeats = len({j.item.id for j in group}), len({j.repeat for j in group})
        mark = ""
        if any(j.input_text is None for j in todo):
            mark, pending_pipeline = " *", True
        print(f"{step:{w_step}} {alias:{w_model}} {prompt:{w_prompt}} {n_lessons:>7} {n_repeats:>7} "
              f"{len(group):>5} {len(group) - len(todo):>6} {len(todo):>6} {tokens:>20} {cost:>9.4f}{mark}")
    print("-" * len(header))
    n_todo = sum(1 for j in jobs if j.cached_id is None)
    budget = f" / budget ${max_usd:.2f}" if max_usd is not None else " (no budget limit)"
    print(f"{len(jobs)} calls, {len(jobs) - n_todo} cached, {n_todo} to run -- estimated cost ${total:.4f}{budget}")
    if pending_pipeline:
        print("* pipeline input not generated yet: estimated from corrected.md")
    print("Estimates use ~3.5 characters/token and do not include reasoning tokens.")
    print_flex(flex, {j.model_alias: j.flex for j in jobs})
    return total


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


@dataclass
class Outcome:
    result: Optional[dict]
    error: Optional[str]
    attempts: int
    latency_s: float
    tokens_in: int
    tokens_out: int
    cost_usd: float


def execute(job: Job) -> Outcome:
    """Run one job with retries. Runs in a worker thread: no DB access here."""
    tokens_in = tokens_out = 0
    error = None
    attempts = 0
    started = time.perf_counter()
    for attempt in range(job.max_retries + 1):
        attempts += 1
        call_started = time.perf_counter()
        try:
            result = job.func(
                job.input_text, item=job.item, provider=job.provider, model=job.model_id, prompt=job.prompt,
                params=job.call_params, timeout=job.timeout,
            )
            if not isinstance(result, dict) or "output" not in result:
                raise TypeError(f"{job.function} must return a dict with 'output', got {type(result).__name__}")
            tokens_in += int(result.get("tokens_in") or 0)
            tokens_out += int(result.get("tokens_out") or 0)
            if result.get("cost_usd") is not None:
                cost = float(result["cost_usd"])
            else:
                cost = compute_cost(job.price, tokens_in, tokens_out)
            return Outcome(result, None, attempts, time.perf_counter() - call_started, tokens_in, tokens_out, cost)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            tokens_in += int(getattr(exc, "tokens_in", 0) or 0)
            tokens_out += int(getattr(exc, "tokens_out", 0) or 0)
            if not getattr(exc, "retryable", True) or attempt == job.max_retries:
                break
            logger.warning("%s: attempt %d failed (%s), retrying", job.label(), attempts, error)
            time.sleep(RETRY_DELAY_S * 2**attempt)
    cost = compute_cost(job.price, tokens_in, tokens_out)
    return Outcome(None, error, attempts, time.perf_counter() - started, tokens_in, tokens_out, cost)


def generation_record(job: Job, outcome: Outcome) -> dict:
    output = outcome.result["output"] if outcome.result else None
    output_format = None
    if output is not None:
        output_format = "text" if isinstance(output, str) else "json"
        if output_format == "json":
            output = json.dumps(output, ensure_ascii=False)
    return {
        "cache_key": job.cache_key,
        "lesson_id": job.item.id,
        "step": job.step,
        "task": job.task,
        "function": job.function,
        "version": job.version,
        "model_alias": job.model_alias,
        "provider": job.provider,
        "model_id": job.model_id,
        "params": job.call_params,
        "prompt_path": job.prompt_path,
        "prompt_sha": sha256(job.prompt),
        "input_source": job.input_source,
        "input_sha": sha256(job.input_text),
        "input_generation_id": job.input_generation_id,
        "repeat_index": job.repeat,
        "output": output,
        "output_format": output_format,
        "tokens_in": outcome.tokens_in,
        "tokens_out": outcome.tokens_out,
        "cost_usd": outcome.cost_usd,
        "latency_s": round(outcome.latency_s, 3),
        "attempts": outcome.attempts,
        "error": outcome.error,
        "meta": (outcome.result or {}).get("meta"),
    }


def git_commit() -> Optional[str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=BENCH_DIR, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=BENCH_DIR, capture_output=True, text=True
        ).stdout.strip()
        return commit + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        print(f"{question} -> no interactive terminal: use --yes to proceed")
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        print()
        return False


class Runner:
    def __init__(self, db: BenchDB, planner: Planner, run_id: int, max_usd: Optional[float], workers: int):
        self.db = db
        self.planner = planner
        self.run_id = run_id
        self.max_usd = max_usd
        self.workers = workers
        self.spent = 0.0
        self.done = 0
        self.failed = 0
        self.skipped = 0
        self.budget_exceeded = False

    def run_step(self, jobs: list[Job], total: int) -> None:
        ready: list[Job] = []
        for job in jobs:
            if job.input_text is None:  # pipeline input generated earlier in this run
                if not self.planner.resolve_input(job):
                    print(f"  SKIP  {job.label()}: input of the previous step not available")
                    self.skipped += 1
                    continue
                if self.db.cached(job.cache_key):
                    continue
                self.planner.estimate(job)
            ready.append(job)

        queue = iter(ready)
        running: dict[Future, Job] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            while True:
                while not self.budget_exceeded and len(running) < self.workers:
                    job = next(queue, None)
                    if job is None:
                        break
                    committed = self.spent + sum(j.est_cost for j in running.values())
                    if self.max_usd is not None and committed + job.est_cost > self.max_usd:
                        self.budget_exceeded = True
                        print(f"  STOP  budget: ${committed:.4f} spent or committed, next call estimated "
                              f"${job.est_cost:.4f}, limit ${self.max_usd:.2f}")
                        break
                    running[pool.submit(execute, job)] = job
                if not running:
                    break
                finished, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in finished:
                    self._record(running.pop(future), future.result(), total)

    def _record(self, job: Job, outcome: Outcome, total: int) -> None:
        self.db.save_prompt(sha256(job.prompt), job.prompt_path, job.prompt)
        self.db.add_generation(self.run_id, generation_record(job, outcome))
        self.spent += outcome.cost_usd
        self.done += 1
        status = "ok    " if outcome.error is None else "FAILED"
        line = (f"  [{self.done}/{total}] {status} {job.label()}  {outcome.latency_s:.1f}s  "
                f"${outcome.cost_usd:.4f}  ({outcome.tokens_in:,}/{outcome.tokens_out:,} tok)")
        if outcome.attempts > 1:
            line += f"  {outcome.attempts} attempts"
        print(line)
        if outcome.error:
            self.failed += 1
            print(f"         {outcome.error}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def print_issues(title: str, issues: list[Issue]) -> None:
    if issues:
        print(f"\n{title}:")
        for issue in issues:
            print(f"    {issue.format()}")


def step_tasks(config: dict, names: Optional[list[str]] = None) -> Optional[set[str]]:
    """Tasks of the steps `names` (default: all the steps of the campaign); None if the steps are invalid."""
    steps = config.get("steps")
    if not isinstance(steps, dict) or not all(isinstance(s, dict) for s in steps.values()):
        return None
    return {step_task(n, steps[n]) for n in (names or steps) if n in steps}


def check(config_path: Path) -> int:
    config = load_config(config_path)
    campaign = (config.get("campaign") or {}).get("name", config_path.stem)
    print(f"Campaign: {campaign}  (dataset {config.get('dataset_version', '?')})")
    print(f"Config:   {config_path}\n")

    items, dataset_issues = load_dataset(config, step_tasks(config))
    width = max((len(i.id) for i in items), default=0)
    for item in items:
        if item.n_errors:
            status = f"{item.n_errors} error(s)"
        elif item.n_warnings:
            status = "OK with warnings"
        else:
            status = "OK"
        print(f"[{item.kind:8}] {item.id:{width}}  {status:18} {describe(item)}")
        for issue in item.issues:
            print(f"    {issue.format()}")

    config_issues = validate_config(config, items)
    print_issues("Dataset", dataset_issues)
    print_issues("Campaign", config_issues)

    all_issues = dataset_issues + config_issues + [i for item in items for i in item.issues]
    n_errors = sum(1 for i in all_issues if i.level == "error")
    n_warnings = len(all_issues) - n_errors
    n_bad = sum(1 for i in items if i.n_errors)
    print(f"\n{len(items)} lesson(s), {n_bad} with errors -- {n_errors} error(s), {n_warnings} warning(s)")
    return 1 if n_errors else 0


def _split(values: Optional[list[str]]) -> Optional[list[str]]:
    """`--steps a,b c` -> [a, b, c]"""
    if not values:
        return None
    return [v for value in values for v in value.split(",") if v]


@dataclass
class Campaign:
    path: Path
    config: dict
    name: str
    items: list[LessonItem]
    steps: list[str]  # selected steps, in campaign order
    models: Optional[list[str]]  # selected model aliases, None = all
    db_path: Path
    judge_confirmed: bool = False  # judge cost already accepted with the generation


def run_campaign(config_path: Path, args: argparse.Namespace) -> int:
    """generate -> score (or a single phase with --only); results in the review app."""
    config = load_config(config_path)
    name = (config.get("campaign") or {}).get("name", config_path.stem)
    all_steps = list(config.get("steps") or {})
    steps = _split(args.steps) or all_steps
    models = _split(args.models)

    items, dataset_issues = load_dataset(config, step_tasks(config, steps))
    issues = dataset_issues + validate_config(config, items, steps)
    issues += [i for item in items for i in item.issues if i.level == "error"]
    for alias in models or []:
        if alias not in (config.get("models") or {}):
            issues.append(Issue("error", f"unknown model alias {alias!r} in --models"))
    errors = [i for i in issues if i.level == "error"]
    if errors:
        print_issues("Cannot run, fix these errors first (details with --check)", errors)
        return 1

    campaign = Campaign(
        path=config_path,
        config=config,
        name=name,
        items=items,
        steps=[s for s in all_steps if s in steps],  # campaign order (pipeline inputs come first)
        models=models,
        db_path=BENCH_DIR / config.get("output_db", "results/bench.sqlite"),
    )
    print(f"Campaign: {name}  (dataset {config.get('dataset_version', '?')})")
    print(f"Steps: {', '.join(campaign.steps)}  |  models: {', '.join(models) if models else 'all'}"
          f"{f'  |  limit: {args.limit} lesson(s)' if args.limit else ''}")
    print(f"Database: {campaign.db_path}\n")

    code = 0
    if args.only in (None, "generate"):
        code, proceed = generate(campaign, args)
        if not proceed or args.only == "generate":
            return code
    if not campaign.db_path.is_file():
        print("No generation yet: nothing to score.")
        return 1

    db = BenchDB(campaign.db_path)
    try:
        jobs, _ = Planner(config, items, db).plan(campaign.steps, args.limit, models)
        print()
        score_jobs(config, jobs, db).print()
        code = max(code, score_judge(campaign, args, jobs, db))
    finally:
        db.close()
    print(f"\nResults: python -m bench.review_app  (campaign {campaign.path.stem})")
    return code


def uses_judge(config: dict, steps: list[str]) -> bool:
    return any(is_judge_metric(metric) for step in steps for metric, _ in metric_specs(config["steps"][step]))


def judge_model(config: dict, args: argparse.Namespace) -> JudgeModel:
    defaults = {**DEFAULTS, **(config.get("defaults") or {})}
    # Judge calls read a whole lesson (and may reason): at least 10 minutes unless judge.timeout_s.
    return JudgeModel.from_config(config, load_pricing(), flex=args.flex, timeout=max(600.0, float(defaults["timeout_s"])),
                                  max_retries=int(defaults["max_retries"]))


def score_judge(campaign: Campaign, args: argparse.Namespace, jobs: list[Job], db: BenchDB) -> int:
    """Judge metrics of the generated outputs: estimate, confirmation, calls. Returns an exit code."""
    config = campaign.config
    if not uses_judge(config, campaign.steps):
        return 0
    judge = judge_model(config, args)
    tasks = plan_judge(config, jobs, db, judge, metric_specs, reference_text, gold_input)
    summary = JudgeSummary()
    rescore_judged(tasks, db, judge, summary)
    tasks = calls_needed(tasks)
    if not tasks:
        summary.print()
        print("Judge: every judgment is cached.")
        return 1 if summary.errors else 0
    budget = config.get("budget") or {}
    max_usd = budget.get("max_usd")
    estimated = print_judge_plan(tasks, judge)
    if max_usd is not None and estimated > max_usd:
        print(f"\nEstimated judge cost ${estimated:.4f} exceeds budget.max_usd ${max_usd:.2f}.")
        return 1
    if args.dry_run:
        return 0
    if (budget.get("dry_run_estimate", True) and not args.yes and not campaign.judge_confirmed
            and not confirm(f"\nRun {len(tasks)} judge scores?")):
        print("Judge skipped.")
        return 1
    workers = args.workers or int((config.get("defaults") or {}).get("workers", DEFAULTS["workers"]))
    print()
    run_judge(tasks, db, judge, workers=workers, max_usd=max_usd, summary=summary)
    summary.print()
    return 1 if summary.failed or summary.errors else 0


def generate(campaign: Campaign, args: argparse.Namespace) -> tuple[int, bool]:
    """Generation phase. Returns (exit code, whether scoring should follow)."""
    config, items, steps, models, db_path = (
        campaign.config, campaign.items, campaign.steps, campaign.models, campaign.db_path
    )
    budget = config.get("budget") or {}
    max_usd = budget.get("max_usd")

    read_db = BenchDB.open_existing(db_path)
    judge_tasks = []
    try:
        jobs, skipped = Planner(config, items, read_db, flex=args.flex).plan(steps, args.limit, models)
        if args.only is None and uses_judge(config, steps):
            judge_tasks = calls_needed(plan_judge(config, jobs, read_db, judge_model(config, args), metric_specs,
                                                  reference_text, gold_input, include_pending=True))
    finally:
        if read_db:
            read_db.close()
    for message in skipped:
        print(f"SKIP  {message}")
    generation_cost = print_plan(jobs, max_usd, flex=args.flex)
    judge_cost = print_judge_plan(judge_tasks, judge_model(config, args)) if judge_tasks else 0.0
    estimated = generation_cost + judge_cost
    if judge_tasks:
        print(f"\nTotal estimated cost ${estimated:.4f} (generation ${generation_cost:.4f} + judge ${judge_cost:.4f})")

    todo = [j for j in jobs if j.cached_id is None]
    if max_usd is not None and estimated > max_usd:
        print(f"\nEstimated cost ${estimated:.4f} exceeds budget.max_usd ${max_usd:.2f}: "
              "reduce the campaign (--limit, --steps, --models) or raise the budget.")
        return 1, False
    if args.dry_run:
        return 0, False
    if not todo:
        print("\nNothing to generate: every call is cached.")
        return 0, True
    question = f"\nRun {len(todo)} calls" + (f" and {len(judge_tasks)} judge scores" if judge_tasks else "") + "?"
    if budget.get("dry_run_estimate", True) and not args.yes and not confirm(question):
        print("Aborted.")
        return 1, False
    campaign.judge_confirmed = True

    db = BenchDB(db_path)
    planner = Planner(config, items, db, flex=args.flex)
    run_id = db.start_run(
        campaign=campaign.name,
        config_path=str(campaign.path),
        config_hash=sha256(campaign.path.read_text(encoding="utf-8-sig")),
        dataset_version=config.get("dataset_version"),
        git_commit=git_commit(),
        args={k: v for k, v in vars(args).items() if k != "config"},
        estimated_usd=estimated,
    )
    workers = args.workers or int((config.get("defaults") or {}).get("workers", DEFAULTS["workers"]))
    runner = Runner(db, planner, run_id, max_usd, workers)
    print(f"\nRun #{run_id}")
    status = "failed"
    try:
        for step in steps:
            step_jobs = [j for j in todo if j.step == step]
            if step_jobs:
                print(f"\n== {step} ({len(step_jobs)} calls)")
                runner.run_step(step_jobs, len(todo))
            if runner.budget_exceeded:
                break
        status = "budget_exceeded" if runner.budget_exceeded else "completed"
    except KeyboardInterrupt:
        status = "interrupted"
        print("\nInterrupted: finished calls are saved, the next launch resumes from the cache.")
    finally:
        db.finish_run(run_id, status, runner.spent)
        db.close()

    print(f"\nRun #{run_id} {status}: {runner.done - runner.failed} generated, {runner.failed} failed, "
          f"{runner.skipped} skipped -- cost ${runner.spent:.4f} (estimated ${estimated:.4f})")
    if runner.failed:
        print("Failed calls are retried at the next launch.")
    return (0 if status == "completed" and not runner.failed else 1), status != "interrupted"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.run", description="Run a bench campaign.")
    parser.add_argument("config", type=Path, help="campaign YAML file (e.g. bench/configs/campaign.yaml)")
    parser.add_argument("--check", action="store_true", help="validate the config and the dataset, then exit")
    parser.add_argument("--dry-run", action="store_true", help="show the calls to run and their estimated cost")
    parser.add_argument("--limit", type=int, help="number of lessons per dataset (quick test)")
    parser.add_argument("--steps", nargs="+", help="subset of steps")
    parser.add_argument("--models", nargs="+", help="subset of model aliases")
    parser.add_argument("--only", choices=["generate", "score"], help="run a single phase")
    parser.add_argument("--workers", type=int, help="parallel calls (default: defaults.workers or 1)")
    parser.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--flex", action="store_true",
                        help="OpenRouter flex tier for the models with a flex ratio in configs/pricing.yaml")
    parser.add_argument("--verbose", "-v", action="store_true", help="show the logs of the app code")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not args.verbose:
        # The app logs every LLM error / ignored line; the bench records them in the generations.
        logging.getLogger("services").setLevel(logging.CRITICAL)

    if not args.config.is_file():
        parser.error(f"config file not found: {args.config}")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.check:
        return check(args.config)
    return run_campaign(args.config, args)


if __name__ == "__main__":
    sys.exit(main())
