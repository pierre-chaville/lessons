"""Adapters between the bench and the app code.

Every adapter follows the same contract:

    def <step>(text: str, *, item, model: str, prompt: str, params: dict, timeout: float) -> dict
        returns {"output": str | dict, "tokens_in": int, "tokens_out": int,
                 "cost_usd": float | None, "meta": dict}

- `text`: input of the step (content of initial.md / corrected.md / previous output)
- `item`: the LessonItem being processed
- `model`: model id in LiteLLM format (`openai/gpt-5.4`, `anthropic/...`, `openrouter/...`)
- `prompt`: content of the prompt file
- `params`: model params of the campaign + step-specific params
- `timeout`: timeout of each LLM call, in seconds

`cost_usd` is None when the provider does not report it; the runner computes it from the
model price. `meta` holds step-specific diagnostics stored with the generation.
An adapter raises StepError when the generation must be recorded as failed.

For the cost estimate before a run, `estimate_<function>(text, prompt, params)` returns the
expected (tokens_in, tokens_out) of one call; `estimate_tokens` is used when it is not defined.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, Optional

from bench.dataset import Segment, format_transcript, parse_transcript

# Bump when the code of an adapter (or of the app function it calls) changes. See README "Cache".
VERSIONS = {
    "correction": 1,
}

_PROVIDERS = {"openai": "OpenAI", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
_LLM_PARAMS = {"temperature", "max_tokens", "thinking_mode", "use_flex"}


class StepError(RuntimeError):
    """The generation failed and must be recorded as such (and retried at the next launch).

    `retryable=False` when retrying in the same run cannot help (invalid params, truncation).
    `tokens_in` / `tokens_out` are the tokens already consumed, counted in the cost.
    """

    def __init__(self, message: str, *, retryable: bool = True, tokens_in: int = 0, tokens_out: int = 0):
        super().__init__(message)
        self.retryable = retryable
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


def split_model_id(model: str) -> tuple[str, str]:
    """`openai/gpt-5.4` -> ("OpenAI", "gpt-5.4"). OpenRouter ids keep their own prefix."""
    prefix, sep, name = model.partition("/")
    provider = _PROVIDERS.get(prefix.lower())
    if not sep or not name or provider is None:
        raise StepError(
            f"unsupported model id {model!r}: the app supports {', '.join(p + '/...' for p in _PROVIDERS)}",
            retryable=False,
        )
    return provider, name


def _check_params(params: dict, step_params: set[str]) -> None:
    unknown = set(params) - _LLM_PARAMS - step_params
    if unknown:
        raise StepError(
            f"unknown params {sorted(unknown)} (allowed: {sorted(_LLM_PARAMS | step_params)})", retryable=False
        )


def approx_tokens(text: str) -> int:
    """Rough token count for cost estimates (~3.5 characters per token for French)."""
    return math.ceil(len(text) / 3.5)


def estimate_tokens(text: str, prompt: str, params: dict) -> tuple[int, int]:
    """Default estimate: one call reading prompt + input and writing about as much as the input."""
    tokens_in = approx_tokens(prompt) + approx_tokens(text)
    return tokens_in, min(approx_tokens(text), int(params.get("max_tokens") or 10**9))


def _build_llm(model: str, params: dict, default_max_tokens: int):
    from services.llm_utils import get_llm_model

    provider, model_name = split_model_id(model)
    return get_llm_model(
        provider=provider,
        model=model_name,
        temperature=params.get("temperature", 0.0),
        max_tokens=params.get("max_tokens", default_max_tokens),
        thinking_mode=params.get("thinking_mode"),
        use_flex=bool(params.get("use_flex", False)),
    )


class RecordingLLM:
    """Wraps a LangChain chat model to record usage, raw outputs and errors.

    App functions often catch LLM errors and fall back to their input; the bench must
    not score such a fallback as a real generation, so errors are recorded here.
    """

    def __init__(self, llm, timeout: Optional[float]):
        self._llm = llm
        self._timeout = timeout
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0
        self.outputs: list[str] = []
        self.errors: list[str] = []
        self.truncated = 0

    async def ainvoke(self, prompt, **kwargs):
        self.calls += 1
        try:
            response = await asyncio.wait_for(self._llm.ainvoke(prompt, **kwargs), self._timeout)
        except asyncio.TimeoutError:
            self.errors.append(f"timeout after {self._timeout}s")
            raise
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__}: {exc}")
            raise
        usage = getattr(response, "usage_metadata", None) or {}
        self.tokens_in += int(usage.get("input_tokens") or 0)
        self.tokens_out += int(usage.get("output_tokens") or 0)
        metadata = getattr(response, "response_metadata", None) or {}
        if metadata.get("finish_reason") == "length" or metadata.get("stop_reason") == "max_tokens":
            self.truncated += 1
        self.outputs.append(str(getattr(response, "content", response) or ""))
        return response

    def raise_if_failed(self) -> None:
        usage = {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out}
        if self.errors:
            raise StepError(f"{len(self.errors)}/{self.calls} LLM call(s) failed; first: {self.errors[0]}", **usage)
        if self.truncated:
            raise StepError(
                f"{self.truncated}/{self.calls} LLM output(s) truncated (max_tokens reached)", retryable=False, **usage
            )


# --------------------------------------------------------------------------- #
# Correction
# --------------------------------------------------------------------------- #

_CORRECTION_PARAMS = {"segments_per_group", "max_concurrency", "glossary"}


def _load_glossary_rules() -> list:
    from sqlmodel import Session

    from database import engine
    from services.glossary_apply import load_glossary_rules

    with Session(engine) as session:
        return load_glossary_rules(session)


async def _correct_segments(
    segments: list[Segment], llm, prompt: str, segments_per_group: int, max_concurrency: int
) -> list[str]:
    """Same grouping and per-group call as `services.correction.correct_transcript_async`."""
    from services.correction import correct_segment_group

    app_segments = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    groups = [
        list(enumerate(app_segments[i : i + segments_per_group], start=i))
        for i in range(0, len(app_segments), segments_per_group)
    ]
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_group(group):
        async with semaphore:
            return await correct_segment_group(group, llm, prompt)

    results = await asyncio.gather(*(run_group(g) for g in groups))
    corrected = sorted((pair for group in results for pair in group), key=lambda pair: pair[0])
    return [text for _, text in corrected]


def _count_unparsed_lines(outputs: list[str], group_size: int) -> int:
    """Output lines the app parser could not use (e.g. the model ignored the `<id>|<text>` format)."""
    from services.correction import _parse_compact_corrections

    unparsed = 0
    for output in outputs:
        lines = [
            line.strip()
            for line in output.splitlines()
            if line.strip() and not line.strip().startswith("```") and line.strip().upper() != "NONE"
        ]
        unparsed += max(0, len(lines) - len(_parse_compact_corrections(output, group_size)))
    return unparsed


def estimate_correction(text: str, prompt: str, params: dict) -> tuple[int, int]:
    """The prompt is sent once per group; the model only returns the segments it changes."""
    from services.correction import COMPACT_CORRECTION_OUTPUT_INSTRUCTIONS

    segments, _ = parse_transcript(text)
    groups = max(1, math.ceil(len(segments) / int(params.get("segments_per_group", 10))))
    per_group = approx_tokens(prompt) + approx_tokens(COMPACT_CORRECTION_OUTPUT_INSTRUCTIONS) + 10
    segment_tokens = sum(approx_tokens(s.text) + 2 for s in segments)
    # Assume half of the text is rewritten (conservative: most segments are unchanged).
    return groups * per_group + segment_tokens, math.ceil(segment_tokens * 0.5)


def correction(text: str, *, item: Any, model: str, prompt: str, params: dict, timeout: float) -> dict:
    """Transcript correction, through `services.correction.correct_segment_group`.

    Step params:
    - segments_per_group (default 10, as the app worker)
    - max_concurrency (default 10)
    - glossary (default False): apply the glossary of the app DB after the LLM, as the app does.
      The glossary content is not part of the cache key: bump the step version when it changes.
    """
    _check_params(params, _CORRECTION_PARAMS)
    segments, problems = parse_transcript(text)
    if problems or not segments:
        raise StepError(
            f"input is not a valid transcript ({len(problems)} invalid lines, {len(segments)} segments)",
            retryable=False,
        )

    segments_per_group = int(params.get("segments_per_group", 10))
    llm = RecordingLLM(_build_llm(model, params, default_max_tokens=16000), timeout)
    corrected_texts = asyncio.run(
        _correct_segments(
            segments,
            llm,
            prompt,
            segments_per_group=segments_per_group,
            max_concurrency=int(params.get("max_concurrency", 10)),
        )
    )
    llm.raise_if_failed()

    corrected = [Segment(s.start, s.end, t, s.line) for s, t in zip(segments, corrected_texts)]
    changed = sum(1 for a, b in zip(segments, corrected) if a.text != b.text)

    glossary_report: list = []
    if params.get("glossary"):
        from services.glossary_apply import apply_glossary_to_segments_with_report

        data = [{"start": s.start, "end": s.end, "text": s.text} for s in corrected]
        data, glossary_report = apply_glossary_to_segments_with_report(data, _load_glossary_rules())
        corrected = [Segment(s.start, s.end, d["text"], s.line) for s, d in zip(corrected, data)]

    return {
        "output": format_transcript(corrected),
        "tokens_in": llm.tokens_in,
        "tokens_out": llm.tokens_out,
        "cost_usd": None,
        "meta": {
            "llm_calls": llm.calls,
            "segments": len(segments),
            "segments_changed_by_llm": changed,
            "unparsed_output_lines": _count_unparsed_lines(llm.outputs, segments_per_group),
            "glossary_replacements": glossary_report,
        },
    }
