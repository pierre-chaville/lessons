"""Extract sources from edited transcript parts using LLM"""

import asyncio
from typing import List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson
from schemas import EditedParagraph, Source, Metadata
from config import load_config
from .llm_utils import get_llm_model
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


# Input/Output models for structured output
class EditedParagraphInput(BaseModel):
    """Input: Edited paragraph text for source extraction"""

    paragraph_number: int = Field(description="Paragraph number (0-indexed)")
    text: str = Field(description="Edited paragraph text to extract sources from")


def create_source_output_model(allowed_types: List[str], type_descriptions: dict = None):
    """Create a SourceOutput model with enum constraint on type field"""
    
    # Build type description for prompt with descriptions if available
    if allowed_types:
        if type_descriptions:
            # Format: "Type1 (description1), Type2 (description2), ..."
            type_list_with_descriptions = [
                f"{t} ({type_descriptions.get(t, '')})" if type_descriptions.get(t) else t
                for t in allowed_types
            ]
            type_description = f"Type of source as per Sefaria documentation and api. Must be one of: {', '.join(type_list_with_descriptions)}"
        else:
            type_description = f"Type of source as per Sefaria documentation and api. Must be one of: {', '.join(allowed_types)}"
    else:
        type_description = "Type of source as per Sefaria documentation and api (e.g., Torah, Mishnah, Gemara, Midrash, etc.)"
    
    # Store allowed_types in closure for validator
    allowed_types_set = set(allowed_types) if allowed_types else None
    
    class SourceOutput(BaseModel):
        """A source citation found in the edited text"""

        paragraph_number: int = Field(
            description="Paragraph number (0-indexed) where the source is cited"
        )
        type: str | None = Field(
            default=None,
            description=type_description,
            json_schema_extra={
                "enum": list(allowed_types) if allowed_types else None
            }
        )
        work: str | None = Field(description="Work title (e.g., Pirkei Avot), as per Sefaria documentation and api")
        ref: str | None = Field(description="Reference to the source (e.g., 4.2), as per Sefaria documentation and api")
        standard_slug: str | None = Field(
            description="Standard slug in Sefaria for the source (e.g., Pirkei_Avot.4.2), as per Sefaria api"
        )
        original_text: str = Field(
            description="Text from the source in the original language"
        )
        translation_text: str = Field(
            description="Text from the source in the lesson language (fr)"
        )
        cited_excerpt: str = Field(
            description="The exact excerpt from the edited text that cites this source. "
            "This should be the text as it appears in the edited version, matching exactly "
            "how the source is mentioned in the text. This is used to mark the citation."
        )
        confidence: float | None = Field(
            description="Confidence score between 0 and 1 [1 = high confidence, 0 = low confidence, 0.5 = medium confidence]"
        )
        
        @field_validator('type')
        @classmethod
        def validate_type(cls, v, info):
            if v is None:
                return v
            if allowed_types_set and v not in allowed_types_set:
                # Log warning but don't fail - allow it but warn
                logger.warning(f"Source type '{v}' not in allowed types: {list(allowed_types_set)}")
            return v
    
    return SourceOutput


# Default SourceOutput (will be replaced with config-based one)
SourceOutput = create_source_output_model([])


def create_source_extraction_output_model(source_output_model):
    """Create SourceExtractionOutput model with the specified SourceOutput model"""
    
    class SourceExtractionOutput(BaseModel):
        """Output: Extracted sources from edited paragraphs"""

        sources: List[source_output_model] = Field(
            default=[],
            description="List of sources cited in these edited paragraphs. "
            "If no sources are found, return an empty list.",
        )
    
    return SourceExtractionOutput


# Default SourceExtractionOutput (will be replaced with config-based one)
SourceExtractionOutput = create_source_extraction_output_model(SourceOutput)


async def extract_sources_from_paragraphs_with_retry(
    paragraphs: List[EditedParagraphInput],
    llm_with_structure,
    extraction_prompt: str,
    max_retries: int = MAX_RETRIES,
) -> List[SourceOutput]:
    """
    Extract sources from edited paragraphs with retry logic for rate limits.

    Args:
        paragraphs: The edited paragraphs to extract sources from
        llm_with_structure: LLM model with structured output
        extraction_prompt: Prompt for source extraction
        max_retries: Maximum number of retry attempts

    Returns:
        List of SourceOutput objects
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await extract_sources_from_paragraphs(
                paragraphs, llm_with_structure, extraction_prompt
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


async def extract_sources_from_paragraphs(
    paragraphs: List[EditedParagraphInput], llm_with_structure, extraction_prompt: str
) -> List[SourceOutput]:
    """
    Extract sources from edited paragraphs using the LLM with structured output.

    Args:
        paragraphs: The edited paragraphs to extract sources from
        llm_with_structure: LLM model with structured output
        extraction_prompt: Prompt for source extraction

    Returns:
        List of SourceOutput objects
    """
    try:
        # Create the prompt with the edited paragraphs
        paragraphs_text = "\n".join(
            [
                f"Paragraph {p.paragraph_number}: {p.text}"
                for p in paragraphs
                if p.text
            ]
        )
        full_prompt = (
            f"{extraction_prompt}\n\n"
            "Edited paragraphs to analyze (use the paragraph number in your output):\n"
            f"{paragraphs_text}"
        )

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
        
        # Get allowed source types from config
        source_types_config = config.get("source_types", {})
        allowed_types = list(source_types_config.keys()) if source_types_config else []
        type_descriptions = source_types_config if source_types_config else {}
        
        # Create models with enum constraint
        SourceOutputModel = create_source_output_model(allowed_types, type_descriptions)
        SourceExtractionOutputModel = create_source_extraction_output_model(SourceOutputModel)

        # Build type description for prompt with descriptions
        if allowed_types:
            if type_descriptions:
                # Format with descriptions: "Type1 (description1), Type2 (description2), ..."
                type_list_with_descriptions = [
                    f"{t} ({type_descriptions.get(t, '')})" if type_descriptions.get(t) else t
                    for t in allowed_types
                ]
                type_instruction = f"Type of source. MUST be one of: {', '.join(type_list_with_descriptions)}"
            else:
                type_list = ", ".join(allowed_types)
                type_instruction = f"Type of source. MUST be one of: {type_list}"
        else:
            type_instruction = "Type of source (e.g., Torah, Mishnah, Gemara, Midrash, Rashi, etc.)"

        extraction_prompt = extraction_config.get(
            "prompt",
            "Analyze the following edited paragraphs and extract all sources (citations, references to religious texts, etc.) mentioned in them. "
            "For each source, provide:\n"
            "- paragraph_number: Paragraph number (0-indexed) where the source appears\n"
            f"- type: {type_instruction}\n"
            "- work: Work title (e.g., Pirkei Avot, Bereshit, etc.) using Sefaria classification\n"
            "- ref: Reference (e.g., 4.2, 18:1, etc.) using Sefaria classification\n"
            "- standard_slug: Standard Sefaria slug if known (e.g., Pirkei_Avot.4.2) using Sefaria api\n"
            "- original_text: The original text from the source in Hebrew/Aramaic\n"
            "- translation_text: The translation of the source text\n"
            "- cited_excerpt: The exact excerpt from the edited text that cites this source. "
            "This must match exactly how the source appears in the text.\n"
            "- confidence: Your confidence in this extraction (0-1)\n\n"
            "If no sources are found, return an empty list. "
            "Be thorough but only extract sources that are clearly mentioned in the text.",
        )
        
        # If we have allowed types, append them to the prompt with descriptions
        if allowed_types:
            if type_descriptions:
                # Create a formatted list with descriptions
                type_details = []
                for t in allowed_types:
                    desc = type_descriptions.get(t, '')
                    if desc:
                        type_details.append(f"  - {t}: {desc}")
                    else:
                        type_details.append(f"  - {t}")
                extraction_prompt += f"\n\nIMPORTANT: The 'type' field MUST be one of these values:\n" + "\n".join(type_details)
            else:
                extraction_prompt += f"\n\nIMPORTANT: The 'type' field MUST be one of these values: {', '.join(allowed_types)}"

        # Get LLM model
        llm = get_llm_model(task_name="extraction")

        # Add structured output with the config-based model
        llm_with_structure = llm.with_structured_output(SourceExtractionOutputModel)

        # Convert edited_transcript to EditedParagraph objects
        edited_parts = [
            EditedParagraph(**part_dict) for part_dict in lesson.edited_transcript
        ]

        # Group paragraphs by word count
        words_per_group = extraction_config.get("words_per_group", 1000)
        paragraph_inputs: List[EditedParagraphInput] = []
        for idx, part in enumerate(edited_parts):
            paragraph_inputs.append(
                EditedParagraphInput(paragraph_number=idx, text=part.text)
            )

        paragraph_groups: List[List[EditedParagraphInput]] = []
        current_group: List[EditedParagraphInput] = []
        current_word_count = 0
        for paragraph in paragraph_inputs:
            word_count = len(paragraph.text.split()) if paragraph.text else 0
            if current_group and current_word_count + word_count > words_per_group:
                paragraph_groups.append(current_group)
                current_group = []
                current_word_count = 0
            current_group.append(paragraph)
            current_word_count += word_count
        if current_group:
            paragraph_groups.append(current_group)

        logger.info(
            f"Extracting sources from lesson {lesson_id}: {len(edited_parts)} edited paragraphs "
            f"in {len(paragraph_groups)} groups (~{words_per_group} words/group) "
            f"with max concurrency {max_concurrency}"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(group):
            async with semaphore:
                return await extract_sources_from_paragraphs_with_retry(
                    group, llm_with_structure, extraction_prompt
                )

        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in paragraph_groups]
        results = await asyncio.gather(*tasks)

        # Accumulate sources per paragraph
        sources_by_paragraph: List[List[Source]] = [[] for _ in edited_parts]
        for group_sources in results:
            for src in group_sources:
                if src.paragraph_number < 0 or src.paragraph_number >= len(edited_parts):
                    logger.warning(
                        "Skipping source with invalid paragraph_number %s",
                        src.paragraph_number,
                    )
                    continue
                sources_by_paragraph[src.paragraph_number].append(
                    Source(
                        type=str(src.type) if src.type is not None else None,
                        work=src.work,
                        ref=src.ref,
                        standard_slug=src.standard_slug,
                        original_text=src.original_text,
                        translation_text=src.translation_text,
                        cited_excerpt=src.cited_excerpt,
                        confidence=src.confidence,
                    )
                )

        # Update edited parts with extracted sources
        for idx, part in enumerate(edited_parts):
            part.sources = sources_by_paragraph[idx]

        # Update lesson with edited transcript (convert to dicts for JSON storage)
        lesson.edited_transcript = [part.model_dump() for part in edited_parts]

        # Save extraction metadata
        extraction_provider = extraction_config.get("provider", config.get("provider"))
        metadata = Metadata(
            provider=extraction_provider,
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
            f"{total_sources} sources found across {len(edited_parts)} edited paragraphs"
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
