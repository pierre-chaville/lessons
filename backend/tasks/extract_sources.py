"""Extract sources from edited transcript parts using LLM"""

import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson, EditedPart, Source, Metadata
from config import load_config
from .llm_utils import get_llm_model
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


# Input/Output models for structured output
class EditedPartInput(BaseModel):
    """Input: Edited part text for source extraction"""

    text: str = Field(description="Edited text to extract sources from")


class SourceOutput(BaseModel):
    """A source citation found in the edited text"""

    type: str | None = Field(
        description="Type of source (e.g., Torah, Mishnah, Gemara, Midrash, etc.)"
    )
    work: str | None = Field(description="Work title (e.g., Pirkei Avot)")
    ref: str | None = Field(description="Reference to the source (e.g., 4.2)")
    standard_slug: str | None = Field(
        description="Standard slug in Sefaria for the source (e.g., Pirkei_Avot.4.2)"
    )
    original_text: str | None = Field(
        description="Relevant quote or text from the source in the original language"
    )
    translation_text: str | None = Field(
        description="Relevant quote or text from the source in the lesson language (fr)"
    )
    cited_excerpt: str | None = Field(
        description="The exact excerpt from the edited text that cites this source. "
        "This should be the text as it appears in the edited version, matching exactly "
        "how the source is mentioned in the text. This is used to mark the citation."
    )
    confidence: float | None = Field(
        description="Confidence score between 0 and 1 [1 = high confidence, 0 = low confidence, 0.5 = medium confidence]"
    )


class SourceExtractionOutput(BaseModel):
    """Output: Extracted sources from edited part"""

    sources: List[SourceOutput] = Field(
        default=[],
        description="List of sources cited in this edited part. "
        "If no sources are found, return an empty list.",
    )


async def extract_sources_from_part_with_retry(
    edited_text: str,
    llm_with_structure,
    extraction_prompt: str,
    max_retries: int = MAX_RETRIES,
) -> List[SourceOutput]:
    """
    Extract sources from an edited part with retry logic for rate limits.

    Args:
        edited_text: The edited text to extract sources from
        llm_with_structure: LLM model with structured output
        extraction_prompt: Prompt for source extraction
        max_retries: Maximum number of retry attempts

    Returns:
        List of SourceOutput objects
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await extract_sources_from_part(
                edited_text, llm_with_structure, extraction_prompt
            )

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


async def extract_sources_from_part(
    edited_text: str, llm_with_structure, extraction_prompt: str
) -> List[SourceOutput]:
    """
    Extract sources from an edited part using the LLM with structured output.

    Args:
        edited_text: The edited text to extract sources from
        llm_with_structure: LLM model with structured output
        extraction_prompt: Prompt for source extraction

    Returns:
        List of SourceOutput objects
    """
    try:
        # Create the prompt with the edited text
        full_prompt = f"{extraction_prompt}\n\nEdited text to analyze:\n{edited_text}"

        # Call LLM with structured output
        result = await llm_with_structure.ainvoke(full_prompt)

        # Return the sources (or empty list if None)
        return result.sources if result.sources else []

    except Exception as e:
        logger.error(f"Error extracting sources from edited part: {e}", exc_info=True)
        # Return empty list on error
        return []


async def extract_sources_async(
    lesson_id: int,
    max_concurrency: int = 10,
    session: Optional[Session] = None,
) -> bool:
    """
    Extract sources from all edited parts of a lesson.

    Args:
        lesson_id: ID of the lesson
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session (will create one if not provided)

    Returns:
        True if extraction was successful, False otherwise
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

        if not lesson.edited_transcript:
            logger.error(f"Lesson {lesson_id} has no edited transcript to extract sources from")
            return False

        # Load config
        config = load_config()
        extraction_config = config.get("extraction", {})

        extraction_prompt = extraction_config.get(
            "prompt",
            "Analyze the following edited text and extract all sources (citations, references to religious texts, etc.) mentioned in it. "
            "For each source, provide:\n"
            "- type: Type of source (e.g., Torah, Mishnah, Gemara, Midrash, Rashi, etc.)\n"
            "- work: Work title (e.g., Pirkei Avot, Bereshit, etc.)\n"
            "- ref: Reference (e.g., 4.2, 18:1, etc.)\n"
            "- standard_slug: Standard Sefaria slug if known (e.g., Pirkei_Avot.4.2)\n"
            "- original_text: The original text from the source in Hebrew/Aramaic if mentioned\n"
            "- translation_text: The translation of the source text if mentioned\n"
            "- cited_excerpt: The exact excerpt from the edited text that cites this source. "
            "This must match exactly how the source appears in the text.\n"
            "- confidence: Your confidence in this extraction (0-1)\n\n"
            "If no sources are found, return an empty list. "
            "Be thorough but only extract sources that are clearly mentioned in the text.",
        )

        # Get LLM model
        llm = get_llm_model(task_name="extraction")

        # Add structured output
        llm_with_structure = llm.with_structured_output(SourceExtractionOutput)

        # Convert edited_transcript to EditedPart objects
        edited_parts = [
            EditedPart(**part_dict) for part_dict in lesson.edited_transcript
        ]

        logger.info(
            f"Extracting sources from lesson {lesson_id}: {len(edited_parts)} edited parts "
            f"with max concurrency {max_concurrency}"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(part):
            async with semaphore:
                return await extract_sources_from_part_with_retry(
                    part.text, llm_with_structure, extraction_prompt
                )

        # Process all parts in parallel (with concurrency limit)
        tasks = [process_with_semaphore(part) for part in edited_parts]
        results = await asyncio.gather(*tasks)

        # Update edited parts with extracted sources
        for part, sources_output in zip(edited_parts, results):
            # Convert SourceOutput to Source objects
            part.sources = [
                Source(
                    type=src.type,
                    work=src.work,
                    ref=src.ref,
                    standard_slug=src.standard_slug,
                    original_text=src.original_text,
                    translation_text=src.translation_text,
                    cited_excerpt=src.cited_excerpt,
                    confidence=src.confidence,
                )
                for src in sources_output
            ]

        # Update lesson with edited transcript (convert to dicts for JSON storage)
        lesson.edited_transcript = [part.model_dump() for part in edited_parts]

        # Save extraction metadata
        metadata = Metadata(
            provider=config.get("provider"),
            model=extraction_config.get("model"),
            temperature=extraction_config.get("temperature"),
            prompt=extraction_prompt,
        )
        # Note: We might want to store extraction metadata separately or combine with edition metadata
        # For now, we'll update the edited metadata
        lesson.set_edited_metadata(metadata)

        # Commit changes
        session.add(lesson)
        session.commit()

        total_sources = sum(len(part.sources) for part in edited_parts)
        logger.info(
            f"Successfully extracted sources from lesson {lesson_id}: "
            f"{total_sources} sources found across {len(edited_parts)} edited parts"
        )
        return True

    except Exception as e:
        logger.error(f"Error extracting sources from lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False

    finally:
        if should_close_session and session:
            session.close()


def extract_sources(
    lesson_id: int,
    max_concurrency: int = 10,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for extract_sources_async.

    Args:
        lesson_id: ID of the lesson
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session

    Returns:
        True if extraction was successful, False otherwise
    """
    return asyncio.run(
        extract_sources_async(
            lesson_id=lesson_id,
            max_concurrency=max_concurrency,
            session=session,
        )
    )
