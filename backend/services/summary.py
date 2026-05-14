"""Lesson summary generation using LLM"""

import asyncio
from typing import Optional
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson, ModelPreset
from schemas import Metadata
from config import load_config
from .llm_utils import get_llm_model
from models.versioning import ContentType, VersionSource
from services.versioning import update_content
from services.edited_transcript import edited_transcript_markdown
from services.summary_alignment import build_summary_alignment_metadata
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


async def generate_summary_with_retry(
    input_text: str,
    llm,
    summary_prompt: str,
    input_label: str = "Text",
    max_retries: int = MAX_RETRIES,
) -> str:
    """
    Generate summary with retry logic for rate limits.

    Args:
        input_text: Full text to summarize
        llm: LLM model instance
        summary_prompt: Prompt for summary generation
        max_retries: Maximum number of retry attempts

    Returns:
        Generated summary text
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Create the full prompt
            full_prompt = f"{summary_prompt}\n\n{input_label}:\n{input_text}"

            # Call LLM
            response = await llm.ainvoke(full_prompt)

            # Extract text from response
            if hasattr(response, "content"):
                return response.content
            else:
                return str(response)

        except Exception as e:
            last_error = e
            error_message = str(e).lower()

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


async def generate_summary_async(
    lesson_id: int,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Generate a summary for a lesson using LLM.

    Args:
        lesson_id: ID of the lesson to summarize
        prompt_type: Name of the prompt to use from config.summary.prompts (uses first if not specified)
        session: Optional SQLModel session (will create one if not provided)

    Returns:
        True if summary generation was successful, False otherwise
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

        # Get edited transcript to summarize
        if not lesson.edited_transcript:
            logger.error(f"Lesson {lesson_id} has no edited transcript to summarize")
            return False

        edited_text = edited_transcript_markdown(lesson.edited_transcript).strip()

        if not edited_text:
            logger.error(f"Lesson {lesson_id} has empty edited transcript")
            return False

        logger.info(
            f"Generating summary for lesson {lesson_id} "
            f"({len(edited_text)} characters)"
        )

        # Load config
        config = load_config()
        summary_config = config.get("summary", {})

        # Get prompts list
        prompts = summary_config.get("prompts", [])

        # Handle old config format (single 'prompt' field) for backward compatibility
        if not prompts and "prompt" in summary_config:
            prompts = [{"name": "Default", "text": summary_config["prompt"]}]

        # Use selected prompt for the main summary
        selected_prompt = None
        if prompt_type:
            for p in prompts:
                if p.get("name") == prompt_type:
                    selected_prompt = p
                    break

        if not selected_prompt and prompts:
            selected_prompt = prompts[0]

        summary_prompt = selected_prompt.get("text") if isinstance(selected_prompt, dict) else None
        selected_prompt_name = selected_prompt.get("name") if isinstance(selected_prompt, dict) else None

        # Fallback to a default prompt if nothing is configured
        if not summary_prompt:
            summary_prompt = (
                "Please provide a concise summary of the following lesson."
            )

        max_length = (
            selected_prompt.get("max_length", 300)
            if isinstance(selected_prompt, dict)
            else summary_config.get("max_length", 300)
        )
        try:
            max_length = int(max_length)
        except (TypeError, ValueError):
            max_length = 300
        max_length = max(1, max_length)
        summary_max_tokens = max_length * 2

        # Add max_length instruction to prompt if specified
        if max_length:
            summary_prompt = (
                f"{summary_prompt}\n\nPlease keep the summary under {max_length} words."
            )

        summary_model_preset = None
        summary_model_preset_id = (
            selected_prompt.get("model_preset_id")
            if isinstance(selected_prompt, dict)
            else None
        )
        if summary_model_preset_id is not None:
            summary_model_preset = session.get(ModelPreset, int(summary_model_preset_id))
            if not summary_model_preset:
                logger.warning(
                    "Summary prompt '%s' references missing model preset id=%s; using fallback task config.",
                    selected_prompt_name,
                    summary_model_preset_id,
                )

        # Get LLM model for summary
        if summary_model_preset:
            llm = get_llm_model(
                provider=summary_model_preset.provider,
                model=summary_model_preset.model_id,
                temperature=summary_model_preset.temperature,
                max_tokens=summary_max_tokens,
                thinking_mode=summary_model_preset.thinking_mode or None,
            )
        else:
            llm = get_llm_model(task_name="summary", max_tokens=summary_max_tokens)

        # Generate summary
        summary = await generate_summary_with_retry(
            input_text=edited_text,
            llm=llm,
            summary_prompt=summary_prompt,
            input_label="Edited Text",
        )

        summary_text = summary.strip()

        # Generate brief abstract from summary using dedicated brief config
        brief_config = config.get("brief", {})
        brief_prompt = brief_config.get("prompt")
        brief_prompt_name = "brief"

        if not brief_prompt:
            logger.error("No brief prompt configured in config.brief.")
            return False

        try:
            brief_max_tokens = int(brief_config.get("max_tokens", 1000))
        except (TypeError, ValueError):
            brief_max_tokens = 1000
        brief_max_tokens = max(1, brief_max_tokens)

        brief_model_preset = None
        brief_model_preset_id = brief_config.get("model_preset_id")
        if brief_model_preset_id is not None:
            try:
                brief_model_preset = session.get(ModelPreset, int(brief_model_preset_id))
            except (TypeError, ValueError):
                brief_model_preset = None
            if not brief_model_preset:
                logger.warning(
                    "Brief config references missing model preset id=%s; using fallback config.",
                    brief_model_preset_id,
                )

        if brief_model_preset:
            brief_llm = get_llm_model(
                provider=brief_model_preset.provider,
                model=brief_model_preset.model_id,
                temperature=brief_model_preset.temperature,
                max_tokens=brief_max_tokens,
                thinking_mode=brief_model_preset.thinking_mode or None,
            )
        else:
            brief_llm = get_llm_model(task_name="summary", max_tokens=brief_max_tokens)
        brief = await generate_summary_with_retry(
            input_text=summary.strip(),
            llm=brief_llm,
            summary_prompt=brief_prompt,
            input_label="Summary",
        )

        brief_text = brief.strip()

        # Save summary metadata (including prompt type names)
        prompt_info = summary_prompt
        if selected_prompt_name:
            prompt_info = f"[summary:{selected_prompt_name}] {summary_prompt}"
        if brief_prompt_name:
            prompt_info += f"\n[brief:{brief_prompt_name}] {brief_prompt}"

        summary_provider = (
            summary_model_preset.provider
            if summary_model_preset
            else config.get("provider", "OpenAI")
        )
        metadata = Metadata(
            provider=summary_provider,
            model=(summary_model_preset.model_id if summary_model_preset else None),
            temperature=(summary_model_preset.temperature if summary_model_preset else None),
            max_tokens=summary_max_tokens,
            prompt=prompt_info,
        )
        base_metadata = metadata.model_dump()
        base_metadata.update(
            build_summary_alignment_metadata(
                summary_markdown=summary_text,
                edited_markdown=edited_text,
            )
        )
        lesson.summary_metadata = base_metadata

        # Commit metadata then persist versioned brief/summary snapshots.
        session.add(lesson)
        session.commit()
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.SUMMARY,
            new_content=summary_text,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Pipeline summary rerun",
        )
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.BRIEF,
            new_content=brief_text,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Pipeline brief rerun",
        )
        session.commit()

        logger.info(
            f"Successfully generated summary for lesson {lesson_id} "
            f"({len(summary)} characters)"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error generating summary for lesson {lesson_id}: {e}", exc_info=True
        )
        if session:
            session.rollback()
        return False

    finally:
        if should_close_session and session:
            session.close()


def generate_summary(
    lesson_id: int,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for generate_summary_async.

    Args:
        lesson_id: ID of the lesson to summarize
        prompt_type: Name of the prompt to use from config.summary.prompts
        session: Optional SQLModel session

    Returns:
        True if summary generation was successful, False otherwise
    """
    return asyncio.run(
        generate_summary_async(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            session=session,
        )
    )
