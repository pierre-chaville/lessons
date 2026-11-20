"""Adapters between the bench and the app code.

Every adapter follows the same contract:

    def <step>(text: str, *, item, provider: str, model: str, prompt: str, params: dict,
               timeout: float) -> dict
        returns {"output": str | dict, "tokens_in": int, "tokens_out": int,
                 "cost_usd": float | None, "meta": dict}

- `text`: input of the step (content of initial.md / corrected.md / previous output)
- `item`: the LessonItem being processed
- `provider`: `openai`, `anthropic` or `openrouter` (case-insensitive)
- `model`: model id as the provider expects it (`gpt-5.4` for openai, `openai/gpt-5.4` for openrouter)
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
import functools
import math
from typing import Any, Optional

from bench.dataset import Segment, format_transcript, parse_transcript

# Bump when the code of an adapter (or of the app function it calls) changes. See README "Cache".
VERSIONS = {
    "correction": 2,  # 2: glossary applied by default
    "edition": 2,
    "summary": 2,
}

PROVIDERS = {"openai": "OpenAI", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
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


def provider_name(provider: str) -> str:
    """`openrouter` -> "OpenRouter" (the name expected by the app's `get_llm_model`)."""
    name = PROVIDERS.get(str(provider).lower())
    if name is None:
        raise StepError(
            f"unsupported provider {provider!r}: the app supports {', '.join(PROVIDERS)}", retryable=False
        )
    return name


def _check_params(params: dict, step_params: set[str]) -> None:
    unknown = set(params) - _LLM_PARAMS - step_params
    if unknown:
        raise StepError(
            f"unknown params {sorted(unknown)} (allowed: {sorted(_LLM_PARAMS | step_params)})", retryable=False
        )


def _parse_input_transcript(text: str) -> list[Segment]:
    segments, problems = parse_transcript(text)
    if problems or not segments:
        raise StepError(
            f"input is not a valid transcript ({len(problems)} invalid lines, {len(segments)} segments)",
            retryable=False,
        )
    return segments


def approx_tokens(text: str) -> int:
    """Rough token count for cost estimates (~3.5 characters per token for French)."""
    return math.ceil(len(text) / 3.5)


def estimate_tokens(text: str, prompt: str, params: dict) -> tuple[int, int]:
    """Default estimate: one call reading prompt + input and writing about as much as the input."""
    tokens_in = approx_tokens(prompt) + approx_tokens(text)
    return tokens_in, min(approx_tokens(text), int(params.get("max_tokens") or 10**9))


async def _close_async_clients(llm) -> None:
    """Close the async HTTP client of a LangChain chat model (ChatOpenAI: root_async_client,
    ChatAnthropic: _async_client once created)."""
    llm = getattr(llm, "_llm", llm)  # RecordingLLM
    clients = [getattr(llm, "root_async_client", None), vars(llm).get("_async_client")]
    for client in clients:
        if client is not None and hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                pass


def run_async(coro, llm):
    """asyncio.run(coro), closing the model's HTTP connections before the event loop closes: otherwise
    httpx closes them when the client is garbage collected, on a closed loop ("Event loop is closed")."""
    async def main():
        try:
            return await coro
        finally:
            await _close_async_clients(llm)

    return asyncio.run(main())


def structured_call(schema, full_prompt: str, *, provider: str, model: str, params: dict,
                    timeout: float) -> tuple[Any, dict]:
    """One LLM call with a structured output (LangChain `with_structured_output`, pydantic `schema`).
    Returns (parsed object, {"tokens_in", "tokens_out"}); raises StepError on failure.
    Param `structured_output_method`: method of with_structured_output (default: the provider
    default, i.e. a forced function call; when the model refuses forced tool calls, e.g. Claude
    with thinking or OpenAI reasoning models, the call is redone with `json_schema`)."""
    method = params.get("structured_output_method")

    def invoke(method: Optional[str]):
        # run_async closes the model's HTTP client: each call needs its own model
        llm = _build_llm(provider, model, params, default_max_tokens=16000)
        structured = llm.with_structured_output(schema, include_raw=True, **({"method": method} if method else {}))

        async def call():
            return await asyncio.wait_for(structured.ainvoke(full_prompt), timeout)

        return run_async(call(), llm)

    try:
        try:
            response = invoke(method)
        except Exception as error:
            if method or not _refuses_forced_tools(error):
                raise
            response = invoke("json_schema")
    except asyncio.TimeoutError:
        raise StepError(f"timeout after {timeout}s")
    raw = response.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    tokens = {"tokens_in": int(usage.get("input_tokens") or 0), "tokens_out": int(usage.get("output_tokens") or 0)}
    metadata = getattr(raw, "response_metadata", None) or {}
    if metadata.get("finish_reason") == "length" or metadata.get("stop_reason") == "max_tokens":
        raise StepError("output truncated (max_tokens reached)", retryable=False, **tokens)
    parsed = response.get("parsed")
    if parsed is None:
        raise StepError(f"invalid structured output: {response.get('parsing_error')}", **tokens)
    return parsed, tokens


_FORCED_TOOL_ERRORS = ("tool_choice", "function tools with reasoning_effort")


def _refuses_forced_tools(error: Exception) -> bool:
    """400 of a model that cannot be forced to call the structured-output tool."""
    text = str(error).lower()
    return "400" in text and any(marker in text for marker in _FORCED_TOOL_ERRORS)


def _build_llm(provider: str, model: str, params: dict, default_max_tokens: int):
    from services.llm_utils import get_llm_model

    return get_llm_model(
        provider=provider_name(provider),
        model=model,
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


@functools.lru_cache(maxsize=1)
def _load_glossary_rules() -> tuple:
    """Glossary of the app DB, read once per process (a run uses the same glossary for every call)."""
    from sqlmodel import Session

    from database import engine
    from services.glossary_apply import load_glossary_rules

    with Session(engine) as session:
        return tuple(load_glossary_rules(session))


def _use_glossary(params: dict) -> bool:
    """Step param `glossary` (default True: the app always applies the glossary)."""
    return bool(params.get("glossary", True))


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


def correction(text: str, *, item: Any, provider: str, model: str, prompt: str, params: dict,
               timeout: float) -> dict:
    """Transcript correction, through `services.correction.correct_segment_group`.

    Step params:
    - segments_per_group (default 10, as the app worker)
    - max_concurrency (default 10)
    - glossary (default True): apply the glossary of the app DB after the LLM, as the app does.
      The glossary content is not part of the cache key: bump the step version when it changes.
    """
    _check_params(params, _CORRECTION_PARAMS)
    segments = _parse_input_transcript(text)

    segments_per_group = int(params.get("segments_per_group", 10))
    llm = RecordingLLM(_build_llm(provider, model, params, default_max_tokens=16000), timeout)
    corrected_texts = run_async(
        _correct_segments(
            segments,
            llm,
            prompt,
            segments_per_group=segments_per_group,
            max_concurrency=int(params.get("max_concurrency", 10)),
        ),
        llm,
    )
    llm.raise_if_failed()

    corrected = [Segment(s.start, s.end, t, s.line) for s, t in zip(segments, corrected_texts)]
    changed = sum(1 for a, b in zip(segments, corrected) if a.text != b.text)

    glossary_report: list = []
    if _use_glossary(params):
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


# --------------------------------------------------------------------------- #
# Edition
# --------------------------------------------------------------------------- #

_EDITION_PARAMS = {"words_per_group", "max_concurrency", "glossary"}


def _word_groups(segments: list[Segment], words_per_group: int) -> list[list[Segment]]:
    """Same grouping as `services.edition.edit_transcript_async`."""
    groups: list[list[Segment]] = []
    current: list[Segment] = []
    count = 0
    for segment in segments:
        words = len(segment.text.split())
        if current and count + words > words_per_group:
            groups.append(current)
            current, count = [], 0
        current.append(segment)
        count += words
    if current:
        groups.append(current)
    return groups


def estimate_edition(text: str, prompt: str, params: dict) -> tuple[int, int]:
    """One call per group (prompt + group text), writing about as much as it reads."""
    from services.edition import PLAIN_TEXT_OUTPUT_INSTRUCTIONS

    segments, _ = parse_transcript(text)
    groups = _word_groups(segments, int(params.get("words_per_group", 1000))) or [[]]
    per_group = approx_tokens(prompt) + approx_tokens(PLAIN_TEXT_OUTPUT_INSTRUCTIONS) + 10
    segment_tokens = sum(approx_tokens(s.text) + 1 for s in segments)
    return len(groups) * per_group + segment_tokens, segment_tokens


def edition(text: str, *, item: Any, provider: str, model: str, prompt: str, params: dict,
            timeout: float) -> dict:
    """Edited version (markdown), through `services.edition.edit_segment_group_with_retry`.

    Step params:
    - words_per_group (default 1000, as the app worker)
    - max_concurrency (default 10)
    - glossary (default True): apply the glossary of the app DB to the output, as the app does.
    The app paragraph post-processing (split of oversized paragraphs) is applied.
    """
    from services.edition import _split_oversized_markdown_paragraphs, edit_segment_group_with_retry

    _check_params(params, _EDITION_PARAMS)
    segments = _parse_input_transcript(text)
    groups = _word_groups(segments, int(params.get("words_per_group", 1000)))
    llm = RecordingLLM(_build_llm(provider, model, params, default_max_tokens=16000), timeout)
    semaphore = asyncio.Semaphore(int(params.get("max_concurrency", 10)))

    async def run_group(group: list[Segment]) -> str:
        app_segments = [{"start": s.start, "end": s.end, "text": s.text} for s in group]
        async with semaphore:
            # The bench retries whole calls itself: no retry inside the app function.
            return await edit_segment_group_with_retry(app_segments, llm, prompt, max_retries=1)

    async def run_all() -> list[str]:
        return await asyncio.gather(*(run_group(g) for g in groups))

    parts = run_async(run_all(), llm)
    llm.raise_if_failed()

    markdown = _split_oversized_markdown_paragraphs("\n\n".join(p.strip() for p in parts if p and p.strip()))
    glossary_report: list = []
    if _use_glossary(params):
        from services.glossary_apply import apply_glossary_to_text_with_report

        markdown, glossary_report = apply_glossary_to_text_with_report(markdown, _load_glossary_rules())
        markdown = _split_oversized_markdown_paragraphs(markdown)
    if not markdown.strip():
        raise StepError("edited text is empty", tokens_in=llm.tokens_in, tokens_out=llm.tokens_out)

    return {
        "output": markdown,
        "tokens_in": llm.tokens_in,
        "tokens_out": llm.tokens_out,
        "cost_usd": None,
        "meta": {
            "llm_calls": llm.calls,
            "groups": len(groups),
            "paragraph_retries": llm.calls - len(groups),  # app retry when a paragraph is too long
            "segments": len(segments),
            "paragraphs": len([b for b in markdown.split("\n\n") if b.strip()]),
            "glossary_replacements": glossary_report,
        },
    }


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #

_SUMMARY_PARAMS = {"glossary"}


def _summary_input(text: str) -> tuple[str, str]:
    """(text to summarize, kind). A markdown text (edited.md, edition output) is sent as is; a
    transcript (pipeline from a correction step) without its timestamps, one segment per line."""
    segments, problems = parse_transcript(text)
    if segments and not problems:
        return "\n".join(s.text for s in segments), "transcript"
    return text.strip(), "text"


def estimate_summary(text: str, prompt: str, params: dict) -> tuple[int, int]:
    source, _ = _summary_input(text)
    tokens_in = approx_tokens(prompt) + approx_tokens(source) + 10
    return tokens_in, min(int(params.get("max_tokens") or 1200), math.ceil(approx_tokens(source) / 3))


def summary(text: str, *, item: Any, provider: str, model: str, prompt: str, params: dict,
            timeout: float) -> dict:
    """Summary (markdown), through `services.summary.generate_summary_with_retry`.

    The app summarizes the edited transcript ("Edited Text"): the input is edited.md in gold mode,
    the edition output in pipeline mode.

    Step params:
    - glossary (default True): apply the glossary of the app DB to the input and the output, as
      the app does.
    max_tokens defaults to 1200, as the app.
    """
    from services.summary import generate_summary_with_retry

    _check_params(params, _SUMMARY_PARAMS)
    source, kind = _summary_input(text)
    if not source:
        raise StepError("input is empty", retryable=False)

    glossary_report: list = []
    rules = None
    if _use_glossary(params):
        from services.glossary_apply import apply_glossary_to_text_with_report

        rules = _load_glossary_rules()
        source, glossary_report = apply_glossary_to_text_with_report(source, rules)

    llm = RecordingLLM(_build_llm(provider, model, params, default_max_tokens=1200), timeout)
    try:
        # The bench retries whole calls itself: no retry inside the app function.
        output = run_async(
            generate_summary_with_retry(source, llm, prompt, input_label="Edited Text", max_retries=1), llm
        )
    except Exception:
        llm.raise_if_failed()
        raise
    llm.raise_if_failed()

    output = str(output or "").strip()
    if rules is not None:
        output, output_report = apply_glossary_to_text_with_report(output, rules)
        glossary_report += output_report
    if not output:
        raise StepError("summary is empty", tokens_in=llm.tokens_in, tokens_out=llm.tokens_out)

    return {
        "output": output,
        "tokens_in": llm.tokens_in,
        "tokens_out": llm.tokens_out,
        "cost_usd": None,
        "meta": {
            "llm_calls": llm.calls,
            "input_kind": kind,
            "glossary_replacements": glossary_report,
        },
    }
