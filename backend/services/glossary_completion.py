"""LLM completion of glossary entries that have no transliteration yet.

Entries added automatically (e.g. after a native-Hebrew correction) only have
their Hebrew form and context. This service sends them in batches to the LLM
configured in ``config.glossary`` (model preset, prompt, max tokens) and asks
for a structured result (``GlossaryCompletionBatch``): transliteration,
aliases, type, capitalization, translation and Sefaria title/reference.
"""

import asyncio
import json
import logging
from typing import Any

from sqlmodel import Session

import crud
from config import load_config
from models import GlossaryEntry, ModelPreset
from schemas.glossary import GlossaryCompletion, GlossaryCompletionBatch
from services.llm_utils import get_llm_model

logger = logging.getLogger(__name__)

GLOSSARY_TASK_TYPE = "glossary"
BATCH_SIZE = 25
MAX_CONCURRENCY = 4
CONTEXT_MAX_CHARS = 600
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2  # seconds
DEFAULT_MAX_TOKENS = 8000

# Error fragments of models that refuse a forced tool call (e.g. reasoning
# models); for those, structured output is retried with the JSON-schema method.
_FORCED_TOOL_ERRORS = ("tool_choice", "function tools with reasoning_effort")


class GlossaryCompletionConfigError(Exception):
    """The glossary completion configuration is unusable (e.g. empty prompt)."""


def enqueue_glossary_completion(session: Session, created_by_id: str | None = None) -> int | None:
    """Create a glossary completion task unless one is already pending/running.

    Returns the id of the created or already active task, or None when no
    entry needs completion.
    """
    active = crud.get_active_task_of_type(session, GLOSSARY_TASK_TYPE)
    if active:
        return active.id
    if crud.count_glossary_entries_to_complete(session) == 0:
        return None
    task = crud.create_task(
        session=session,
        task_type=GLOSSARY_TASK_TYPE,
        parameters={},
        created_by_id=created_by_id,
    )
    return task.id


def _context_excerpt(entry: GlossaryEntry) -> str | None:
    """Context paragraph shortened around the Hebrew form."""
    context = (entry.context_paragraph or "").strip()
    if len(context) <= CONTEXT_MAX_CHARS:
        return context or None
    position = context.find(entry.hebrew)
    if position < 0:
        return context[:CONTEXT_MAX_CHARS] + "…"
    start = max(0, position - CONTEXT_MAX_CHARS // 2)
    end = min(len(context), start + CONTEXT_MAX_CHARS)
    excerpt = context[start:end]
    return ("…" if start > 0 else "") + excerpt + ("…" if end < len(context) else "")


def build_batch_prompt(prompt: str, entries: list[GlossaryEntry]) -> str:
    """Configured prompt followed by the entries to complete, as JSON."""
    payload = [
        {"id": entry.id, "hebrew": entry.hebrew, "context": _context_excerpt(entry)}
        for entry in entries
    ]
    return (
        f"{prompt.strip()}\n\n"
        f"Entries to complete ({len(payload)}):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )


def _refuses_forced_tools(error: Exception) -> bool:
    text = str(error).lower()
    return "400" in text and any(marker in text for marker in _FORCED_TOOL_ERRORS)


async def _invoke_structured(llm, full_prompt: str) -> GlossaryCompletionBatch:
    try:
        return await llm.with_structured_output(GlossaryCompletionBatch).ainvoke(full_prompt)
    except Exception as error:
        if not _refuses_forced_tools(error):
            raise
        logger.info("Model refuses forced tool calls; retrying with json_schema output")
        structured = llm.with_structured_output(GlossaryCompletionBatch, method="json_schema")
        return await structured.ainvoke(full_prompt)


async def complete_batch_with_retry(
    llm, prompt: str, entries: list[GlossaryEntry]
) -> list[GlossaryCompletion]:
    """One structured LLM call for a batch, retried with exponential backoff."""
    full_prompt = build_batch_prompt(prompt, entries)
    for attempt in range(MAX_RETRIES):
        try:
            result = await _invoke_structured(llm, full_prompt)
            if result is None:
                raise ValueError("LLM returned no structured output")
            return list(result.entries)
        except Exception as error:
            if attempt == MAX_RETRIES - 1:
                raise
            delay = INITIAL_RETRY_DELAY * (2 ** attempt)
            logger.warning(
                "Glossary batch failed (attempt %s/%s), retrying in %ss: %s",
                attempt + 1,
                MAX_RETRIES,
                delay,
                error,
            )
            await asyncio.sleep(delay)
    return []


def _completion_fields(entry: GlossaryEntry, completion: GlossaryCompletion) -> dict[str, Any] | None:
    """Fields to store for a completion, or None if it carries no transliteration."""
    translit = (completion.translit or "").strip()
    if not translit:
        return None
    aliases: list[str] = []
    for alias in [*(entry.aliases or []), *completion.aliases]:
        alias = (alias or "").strip()
        if alias and alias != translit and alias not in aliases:
            aliases.append(alias)

    def clean(value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    return {
        "translit": translit,
        "aliases": aliases,
        "type": completion.type.value,
        "case_flag": completion.case_flag.value,
        "translation": clean(completion.translation) or entry.translation,
        "sefaria_title": clean(completion.sefaria_title) or entry.sefaria_title,
        "sefaria_ref": clean(completion.sefaria_ref) or entry.sefaria_ref,
    }


def _build_llm(session: Session, glossary_config: dict[str, Any], use_flex: bool):
    try:
        max_tokens = max(1, int(glossary_config.get("max_tokens", DEFAULT_MAX_TOKENS)))
    except (TypeError, ValueError):
        max_tokens = DEFAULT_MAX_TOKENS

    preset = None
    preset_id = glossary_config.get("model_preset_id")
    if preset_id is not None:
        try:
            preset = session.get(ModelPreset, int(preset_id))
        except (TypeError, ValueError):
            preset = None
        if not preset:
            logger.warning(
                "Glossary config references missing model preset id=%s; using fallback config.",
                preset_id,
            )

    if preset:
        return get_llm_model(
            provider=preset.provider,
            model=preset.model_id,
            temperature=preset.temperature,
            max_tokens=max_tokens,
            thinking_mode=preset.thinking_mode or None,
            use_flex=use_flex,
        )
    return get_llm_model(task_name="glossary", max_tokens=max_tokens, use_flex=use_flex)


async def complete_glossary_entries_async(
    session: Session,
    use_flex: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """Complete every entry without transliteration (or the first ``limit``).

    An entry is only updated if it still has no transliteration when the LLM
    answers, so manual edits made meanwhile are never overwritten. Raises if
    every batch failed.
    """
    config = load_config()
    glossary_config = config.get("glossary") or {}
    prompt = (glossary_config.get("prompt") or "").strip()
    if not prompt:
        raise GlossaryCompletionConfigError("No glossary prompt configured in config.glossary")

    entries = crud.get_glossary_entries_to_complete(session, limit=limit)
    report = {"pending": len(entries), "completed": 0, "skipped": 0, "failed_batches": 0}
    if not entries:
        logger.info("Glossary completion: nothing to complete")
        return report

    llm = _build_llm(session, glossary_config, use_flex)
    batches = [entries[i:i + BATCH_SIZE] for i in range(0, len(entries), BATCH_SIZE)]
    logger.info(
        "Glossary completion: %s entries in %s batches (concurrency %s)",
        len(entries),
        len(batches),
        MAX_CONCURRENCY,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(batch: list[GlossaryEntry]) -> list[GlossaryCompletion] | Exception:
        async with semaphore:
            try:
                return await complete_batch_with_retry(llm, prompt, batch)
            except Exception as error:
                logger.error("Glossary batch failed after retries: %s", error, exc_info=True)
                return error

    results = await asyncio.gather(*(run(batch) for batch in batches))

    for batch, result in zip(batches, results):
        if isinstance(result, Exception):
            report["failed_batches"] += 1
            continue
        by_id = {entry.id: entry for entry in batch}
        for completion in result:
            entry = by_id.pop(completion.id, None)
            if entry is None:
                continue
            session.refresh(entry)
            fields = _completion_fields(entry, completion)
            if fields is None or (entry.translit or "").strip():
                report["skipped"] += 1
                continue
            crud.fill_glossary_entry(session, entry, fields)
            report["completed"] += 1
        report["skipped"] += len(by_id)
    session.commit()

    if report["failed_batches"] == len(batches):
        raise RuntimeError(f"All {len(batches)} glossary completion batches failed")
    logger.info("Glossary completion finished: %s", report)
    return report


def complete_glossary_entries(
    session: Session,
    use_flex: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """Synchronous wrapper for complete_glossary_entries_async (worker)."""
    return asyncio.run(
        complete_glossary_entries_async(session=session, use_flex=use_flex, limit=limit)
    )
