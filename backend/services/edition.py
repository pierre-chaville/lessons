"""Lesson transcript edition using LLM - rewrite in written style with sources"""

import asyncio
from datetime import datetime
from typing import List, Optional
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson, ModelPreset
from schemas import Segment, Metadata
from config import load_config
from .llm_utils import get_llm_model
from models.versioning import ContentType, VersionSource
from services.versioning import update_content
from services.edited_transcript import (
    build_edited_transcript_payload,
    markdown_to_paragraphs,
)
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


async def edit_segment_group_with_retry(
    group: List[Segment],
    llm,
    edition_prompt: str,
    max_retries: int = MAX_RETRIES,
) -> str:
    """
    Edit a group of segments with retry logic for rate limits.

    Args:
        group: List of Segment objects or dicts
        llm_with_structure: LLM model with structured output
        edition_prompt: Prompt for edition
        max_retries: Maximum number of retry attempts

    Returns:
        List of EditedPartOutput objects
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await edit_segment_group(
                group, llm, edition_prompt
            )

        except Exception as e:
            last_error = e
            error_message = str(e).lower()

            # If output was truncated, split group and retry
            if "max_tokens" in error_message or "stop reason" in error_message:
                if len(group) > 1:
                    mid = len(group) // 2
                    logger.warning(
                        "Structured output truncated; splitting group of %s into %s and %s segments.",
                        len(group),
                        mid,
                        len(group) - mid,
                    )
                    first = await edit_segment_group_with_retry(
                        group[:mid],
                        llm,
                        edition_prompt,
                        max_retries=max_retries,
                    )
                    second = await edit_segment_group_with_retry(
                        group[mid:],
                        llm,
                        edition_prompt,
                        max_retries=max_retries,
                    )
                    return "\n\n".join(
                        [part for part in [first.strip(), second.strip()] if part]
                    )

            # Check if it's a rate limit error
            is_rate_limit = (
                "rate limit" in error_message
                or "rate_limit" in error_message
                or "429" in error_message
                or "too many requests" in error_message
                or "quota" in error_message
            )

            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff with jitter
                delay = min(INITIAL_RETRY_DELAY * (2**attempt), MAX_RETRY_DELAY)
                jitter = delay * 0.1  # 10% jitter
                actual_delay = delay + (jitter * (2 * (time.time() % 1) - 1))

                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {actual_delay:.1f}s: {e}"
                )
                await asyncio.sleep(actual_delay)
            elif attempt < max_retries - 1:
                # For other errors, shorter retry
                logger.warning(
                    f"Error on attempt {attempt + 1}/{max_retries}, "
                    f"retrying in {INITIAL_RETRY_DELAY}s: {e}"
                )
                await asyncio.sleep(INITIAL_RETRY_DELAY)
            else:
                # Final attempt failed
                logger.error(f"All {max_retries} attempts failed: {e}")
                raise

    # Should not reach here, but just in case
    raise last_error if last_error else Exception("Unknown error in retry logic")


async def edit_segment_group(
    group: List[Segment],
    llm,
    edition_prompt: str,
) -> str:
    """
    Edit a group of segments using the LLM with structured output.

    Args:
        group: List of Segment objects or dicts
        llm_with_structure: LLM model with structured output
        edition_prompt: Prompt for edition

    Returns:
        List of EditedPartOutput objects
    """
    try:
        # Create prompt with transcript segments.
        segments_text = "\n".join(
            [
                (
                    f"[{segment['start']:.1f}s - {segment['end']:.1f}s] {segment['text']}"
                    if isinstance(segment, dict)
                    else f"[{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}"
                )
                for segment in group
            ]
        )
        full_prompt = (
            f"{edition_prompt}\n\n"
            "Transcript to edit:\n"
            f"{segments_text}"
        )

        response = await llm.ainvoke(full_prompt)
        markdown = response.content if hasattr(response, "content") else str(response)
        markdown = markdown.strip()
        if not markdown:
            raise ValueError("Edition output is empty")
        return markdown

    except Exception as e:
        logger.error(f"Error editing segment group: {e}", exc_info=True)
        # Return original text concatenated on error.
        return " ".join(
            [seg["text"] if isinstance(seg, dict) else seg.text for seg in group]
        )


async def edit_transcript_async(
    lesson_id: int,
    words_per_group: int = 1000,
    max_concurrency: int = 10,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Edit a lesson transcript by processing segments in parallel groups.

    Args:
        lesson_id: ID of the lesson to edit
        words_per_group: Target number of words to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session (will create one if not provided)

    Returns:
        True if edition was successful, False otherwise
    """
    should_close_session = False

    try:
        # Create session if not provided
        if session is None:
            session = Session(engine)
            should_close_session = True

        # Load lesson
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return False

        # Use corrected transcript if available, otherwise use original
        source_transcript = lesson.corrected_transcript or lesson.transcript

        if not source_transcript:
            logger.error(f"Lesson {lesson_id} has no transcript to edit")
            return False

        # Load config
        config = load_config()
        edition_config = config.get("edition", {})

        # Resolve prompt from prompts list (like summary) with backward compat
        prompts = edition_config.get("prompts", [])
        if not prompts and "prompt" in edition_config:
            prompts = [{"name": "Default", "text": edition_config["prompt"]}]

        selected_prompt = None
        edition_prompt = None
        if prompt_type:
            for p in prompts:
                if p.get("name") == prompt_type:
                    selected_prompt = p
                    edition_prompt = p.get("text")
                    break

        if not edition_prompt and prompts:
            selected_prompt = prompts[0]
            edition_prompt = prompts[0].get("text")

        if not edition_prompt:
            edition_prompt = (
                "Rewrite the transcript in clean written language while preserving meaning. "
                "Return only the edited text in Markdown format. "
                "Do not include JSON, metadata, timestamps, or source extraction."
            )

        edition_prompt_max_tokens = (
            selected_prompt.get("max_tokens", 16000)
            if isinstance(selected_prompt, dict)
            else edition_config.get("max_tokens", 16000)
        )
        try:
            edition_prompt_max_tokens = int(edition_prompt_max_tokens)
        except (TypeError, ValueError):
            edition_prompt_max_tokens = 16000
        edition_prompt_max_tokens = max(1, edition_prompt_max_tokens)

        edition_model_preset = None
        edition_model_preset_id = (
            selected_prompt.get("model_preset_id")
            if isinstance(selected_prompt, dict)
            else None
        )
        if edition_model_preset_id is not None:
            try:
                edition_model_preset = session.get(ModelPreset, int(edition_model_preset_id))
            except (TypeError, ValueError):
                edition_model_preset = None
            if not edition_model_preset:
                logger.warning(
                    "Edition prompt '%s' references missing model preset id=%s; using fallback config.",
                    selected_prompt.get("name") if isinstance(selected_prompt, dict) else None,
                    edition_model_preset_id,
                )

        # Get LLM model
        if edition_model_preset:
            llm = get_llm_model(
                provider=edition_model_preset.provider,
                model=edition_model_preset.model_id,
                temperature=edition_model_preset.temperature,
                max_tokens=edition_prompt_max_tokens,
                thinking_mode=edition_model_preset.thinking_mode or None,
            )
        else:
            llm = get_llm_model(task_name="edition", max_tokens=edition_prompt_max_tokens)

        if words_per_group <= 0:
            raise ValueError("words_per_group must be a positive integer")

        # Split segments into groups by word count
        segments = source_transcript
        segment_groups = []
        current_group = []
        current_word_count = 0

        for segment in segments:
            text = segment["text"] if isinstance(segment, dict) else segment.text
            segment_word_count = len(text.split()) if text else 0

            if current_group and current_word_count + segment_word_count > words_per_group:
                segment_groups.append(current_group)
                current_group = []
                current_word_count = 0

            current_group.append(segment)
            current_word_count += segment_word_count

        if current_group:
            segment_groups.append(current_group)

        logger.info(
            f"Editing lesson {lesson_id}: {len(segments)} segments "
            f"in {len(segment_groups)} groups (~{words_per_group} words/group) "
            f"with max concurrency {max_concurrency}"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(group):
            async with semaphore:
                return await edit_segment_group_with_retry(
                    group, llm, edition_prompt
                )

        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in segment_groups]
        results = await asyncio.gather(*tasks)

        markdown = "\n\n".join(part.strip() for part in results if isinstance(part, str) and part.strip()).strip()
        if not markdown:
            raise ValueError("Edited transcript markdown is empty")

        edited_paragraphs = markdown_to_paragraphs(markdown)
        if not edited_paragraphs:
            edited_paragraphs = [markdown]
        edited_data = build_edited_transcript_payload(
            markdown=markdown,
            transcript=segments,
            sources=[[] for _ in edited_paragraphs],
            aligned_at_iso=datetime.utcnow().isoformat(),
        )

        # Save edition metadata
        edition_provider = (
            edition_model_preset.provider
            if edition_model_preset
            else edition_config.get("provider", config.get("provider"))
        )
        metadata = Metadata(
            provider=edition_provider,
            model=(
                edition_model_preset.model_id
                if edition_model_preset
                else edition_config.get("model")
            ),
            temperature=(
                edition_model_preset.temperature
                if edition_model_preset
                else edition_config.get("temperature")
            ),
            max_tokens=edition_prompt_max_tokens,
            prompt=edition_prompt,
        )
        lesson.set_edited_metadata(metadata)

        # Commit metadata then persist versioned content.
        session.add(lesson)
        session.commit()
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.EDITED_TRANSCRIPT,
            new_content=edited_data,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Pipeline edition rerun",
        )
        session.commit()

        logger.info(
            f"Successfully edited lesson {lesson_id} transcript: "
            f"{len(segments)} segments -> {len(edited_paragraphs)} edited paragraphs"
        )
        return True

    except Exception as e:
        logger.error(f"Error editing lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False

    finally:
        if should_close_session and session:
            session.close()


def edit_transcript(
    lesson_id: int,
    words_per_group: int = 1000,
    max_concurrency: int = 10,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for edit_transcript_async.

    Args:
        lesson_id: ID of the lesson to edit
        words_per_group: Target number of words to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        prompt_type: Name of the prompt to use from the prompts list
        session: Optional SQLModel session

    Returns:
        True if edition was successful, False otherwise
    """
    return asyncio.run(
        edit_transcript_async(
            lesson_id=lesson_id,
            words_per_group=words_per_group,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            session=session,
        )
    )
