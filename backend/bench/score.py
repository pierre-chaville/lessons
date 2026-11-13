"""Metrics computation on the generations of a campaign (see README "Metrics").

Deterministic metrics are cheap: they are always re-computed, so a fixed metric applies to the
existing outputs without any new LLM call. LLM-judge metrics are not implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from bench.dataset import LessonItem, format_transcript
from bench.db import BenchDB
from bench.metrics import get_metric_module


def metric_specs(step: dict) -> list[tuple[str, dict]]:
    """`[wer, {length_ratio: {min: 0.6}}]` -> [("wer", {}), ("length_ratio", {"min": 0.6})]"""
    specs = []
    for metric in step.get("metrics") or []:
        if isinstance(metric, dict) and len(metric) == 1:
            name, options = next(iter(metric.items()))
            specs.append((str(name), options if isinstance(options, dict) else {}))
        else:
            specs.append((str(metric), {}))
    return specs


def reference_text(task: str, item: LessonItem) -> Optional[str]:
    """Gold text the metrics of a task compare the output with."""
    if task == "correction":
        return format_transcript(item.corrected or [])
    return None


@dataclass
class ScoreSummary:
    generations: int = 0
    scores: int = 0
    not_implemented: set[str] = field(default_factory=set)
    no_reference: set[str] = field(default_factory=set)

    def print(self) -> None:
        print(f"Scoring: {self.scores} scores on {self.generations} generations")
        if self.not_implemented:
            print(f"  not implemented yet (skipped): {', '.join(sorted(self.not_implemented))}")
        if self.no_reference:
            print(f"  no reference for: {', '.join(sorted(self.no_reference))}")


def score_jobs(config: dict, jobs: list[Any], db: BenchDB) -> ScoreSummary:
    """Score the successful generation of every job (jobs planned by run.Planner)."""
    summary = ScoreSummary()
    for job in jobs:
        if job.cached_id is None:
            continue
        summary.generations += 1
        output = db.generation(job.cached_id)["output"]
        reference = reference_text(job.task, job.item)
        for name, options in metric_specs(config["steps"][job.step]):
            try:
                module = get_metric_module(name)
            except KeyError:
                summary.not_implemented.add(name)
                continue
            if reference is None:
                summary.no_reference.add(f"{job.step}/{name}")
                continue
            result = module.compute(output, input_text=job.input_text, reference=reference, options=options)
            db.upsert_score(job.cached_id, name, options, result.value, result.details)
            summary.scores += 1
    db.commit()
    return summary
