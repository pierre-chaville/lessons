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
from models import Lesson, Metadata
from config import load_config
from .llm_utils import get_llm_model
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


async def generate_summary_with_retry(
    transcript_text: str, llm, summary_prompt: str, max_retries: int = MAX_RETRIES
) -> str:
    """
    Generate summary with retry logic for rate limits.

    Args:
        transcript_text: Full transcript text to summarize
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
            full_prompt = f"{summary_prompt}\n\nTranscript:\n{transcript_text}"

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
    use_corrected: bool = True,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Generate a summary for a lesson using LLM.

    Args:
        lesson_id: ID of the lesson to summarize
        use_corrected: Whether to use corrected_transcript (falls back to transcript if not available)
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

        # Get transcript to summarize
        transcript = None
        if use_corrected and lesson.corrected_transcript:
            transcript = lesson.corrected_transcript
            logger.info(f"Using corrected transcript for lesson {lesson_id}")
        elif lesson.transcript:
            transcript = lesson.transcript
            logger.info(f"Using original transcript for lesson {lesson_id}")
        else:
            logger.error(f"Lesson {lesson_id} has no transcript to summarize")
            return False

        # Combine all segment texts into one string
        transcript_text = ""
        for seg in transcript:
            if isinstance(seg, dict):
                transcript_text += seg["text"] + " "
            else:
                transcript_text += seg.text + " "

        transcript_text = transcript_text.strip()

        if not transcript_text:
            logger.error(f"Lesson {lesson_id} has empty transcript")
            return False

        logger.info(
            f"Generating summary for lesson {lesson_id} "
            f"({len(transcript_text)} characters, {len(transcript)} segments)"
        )

        # Load config
        config = load_config()
        summary_config = config.get("summary", {})

        # Get prompts list
        prompts = summary_config.get("prompts", [])

        # Handle old config format (single 'prompt' field) for backward compatibility
        if not prompts and "prompt" in summary_config:
            prompts = [{"name": "Default", "text": summary_config["prompt"]}]

        # Find the requested prompt or use the first one
        summary_prompt = None
        selected_prompt_name = None
        if prompt_type:
            # Find prompt by name
            for p in prompts:
                if p.get("name") == prompt_type:
                    summary_prompt = p.get("text")
                    selected_prompt_name = p.get("name")
                    break

        # If not found or not specified, use the first prompt
        if not summary_prompt and prompts:
            summary_prompt = prompts[0].get("text")
            selected_prompt_name = prompts[0].get("name")

        # Fallback to a default prompt if nothing is configured
        if not summary_prompt:
            summary_prompt = (
                "Please provide a concise summary of the following lesson transcript."
            )

        max_length = summary_config.get("max_length", 300)

        # Add max_length instruction to prompt if specified
        if max_length:
            summary_prompt = (
                f"{summary_prompt}\n\nPlease keep the summary under {max_length} words."
            )

        # Get LLM model
        llm = get_llm_model(task_name="summary")

        # Generate summary
        summary = await generate_summary_with_retry(
            transcript_text=transcript_text, llm=llm, summary_prompt=summary_prompt
        )

        # Update lesson with summary
        lesson.summary = summary.strip()

        # Save summary metadata (including prompt type name)
        prompt_info = summary_prompt
        if selected_prompt_name:
            prompt_info = f"[{selected_prompt_name}] {summary_prompt}"

        metadata = Metadata(
            provider=config.get("provider"),
            model=summary_config.get("model"),
            temperature=summary_config.get("temperature"),
            prompt=prompt_info,
        )
        lesson.set_summary_metadata(metadata)

        # Commit changes
        session.add(lesson)
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
    use_corrected: bool = True,
    prompt_type: Optional[str] = None,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for generate_summary_async.

    Args:
        lesson_id: ID of the lesson to summarize
        use_corrected: Whether to use corrected_transcript (falls back to transcript if not available)
        prompt_type: Name of the prompt to use from config.summary.prompts
        session: Optional SQLModel session

    Returns:
        True if summary generation was successful, False otherwise
    """
    return asyncio.run(
        generate_summary_async(
            lesson_id=lesson_id,
            use_corrected=use_corrected,
            prompt_type=prompt_type,
            session=session,
        )
    )
