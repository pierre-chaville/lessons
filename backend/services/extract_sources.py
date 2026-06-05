"""Extract sources from edited transcript parts using LLM"""

import asyncio
import json
import re
from typing import Any, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson
from models.model_preset import ModelPreset
from schemas import Metadata
from config import load_config
from .llm_utils import get_llm_model
from services.edited_transcript import edited_transcript_markdown, markdown_to_paragraphs
import crud
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds
DEFAULT_WORDS_PER_GROUP = 3000

COMPACT_EXTRACTION_OUTPUT_INSTRUCTIONS = (
    "Return only valid JSON, no Markdown or code fences. Return [] if no sources are found. "
    "For each source, use compact keys: p=paragraph_number, t=type, w=work, r=ref, "
    "s=standard_slug, o=original_text, tr=translation_text, e=cited_excerpt, c=confidence. "
    "Omit unknown optional values or set them to null."
)


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


def _extract_json_payload(output: str) -> Any:
    cleaned = (output or "").strip()
    if not cleaned:
        return []

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if 0 <= array_start < array_end:
            return json.loads(cleaned[array_start : array_end + 1])
        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        if 0 <= object_start < object_end:
            return json.loads(cleaned[object_start : object_end + 1])
        raise


def _normalize_source_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "paragraph_number": row.get("paragraph_number", row.get("p")),
        "type": row.get("type", row.get("t")),
        "work": row.get("work", row.get("w")),
        "ref": row.get("ref", row.get("r")),
        "standard_slug": row.get("standard_slug", row.get("s")),
        "original_text": row.get("original_text", row.get("o")) or "",
        "translation_text": row.get("translation_text", row.get("tr")) or "",
        "cited_excerpt": row.get("cited_excerpt", row.get("e")) or "",
        "confidence": row.get("confidence", row.get("c")),
    }


def _parse_source_extraction_output(output: str, source_output_model) -> List[SourceOutput]:
    try:
        payload = _extract_json_payload(output)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Could not parse source extraction JSON output: %s", exc)
        return []

    rows = payload.get("sources", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    sources = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            sources.append(source_output_model(**_normalize_source_row(row)))
        except Exception as exc:
            logger.warning("Skipping invalid extracted source row: %s", exc)
    return sources


async def extract_sources_from_paragraphs_with_retry(
    paragraphs: List[EditedParagraphInput],
    llm,
    extraction_prompt: str,
    source_output_model=SourceOutput,
    max_retries: int = MAX_RETRIES,
) -> List[SourceOutput]:
    """
    Extract sources from edited paragraphs with retry logic for rate limits.

    Args:
        paragraphs: The edited paragraphs to extract sources from
        llm: LLM model
        extraction_prompt: Prompt for source extraction
        max_retries: Maximum number of retry attempts

    Returns:
        List of SourceOutput objects
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            return await extract_sources_from_paragraphs(
                paragraphs, llm, extraction_prompt, source_output_model
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
    paragraphs: List[EditedParagraphInput],
    llm,
    extraction_prompt: str,
    source_output_model=SourceOutput,
) -> List[SourceOutput]:
    """
    Extract sources from edited paragraphs using compact JSON output.

    Args:
        paragraphs: The edited paragraphs to extract sources from
        llm: LLM model
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
            f"{COMPACT_EXTRACTION_OUTPUT_INSTRUCTIONS}\n\n"
            "Edited paragraphs to analyze (use the paragraph number in your output):\n"
            f"{paragraphs_text}"
        )

        response = await llm.ainvoke(full_prompt)
        output = response.content if hasattr(response, "content") else str(response)

        return _parse_source_extraction_output(output, source_output_model)

    except Exception as e:
        logger.error(f"Error extracting sources from edited part: {e}", exc_info=True)
        # Return empty list on error
        return []


async def extract_sources_async(
    lesson_id: int,
    max_concurrency: int = 10,
    prompt_type: Optional[str] = None,
    use_flex: bool = False,
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
        
        # Create model used to normalize compact JSON rows.
        SourceOutputModel = create_source_output_model(allowed_types, type_descriptions)

        # Keep type instructions compact because they are repeated for each group.
        if allowed_types:
            type_instruction = f"Allowed t values: {', '.join(allowed_types)}"
        else:
            type_instruction = "Use concise source type names."

        # Resolve prompt from prompts list with backward compat
        prompts = extraction_config.get("prompts", [])
        if not prompts and "prompt" in extraction_config:
            prompts = [{"name": "Default", "text": extraction_config["prompt"]}]

        selected_prompt = None
        extraction_prompt = None
        if prompt_type:
            for p in prompts:
                if p.get("name") == prompt_type:
                    selected_prompt = p
                    extraction_prompt = p.get("text")
                    break

        if not extraction_prompt and prompts:
            selected_prompt = prompts[0]
            extraction_prompt = selected_prompt.get("text")

        if not extraction_prompt:
            extraction_prompt = (
                "Extract explicit source citations or references from the edited paragraphs. "
                "Only extract sources clearly mentioned in the text. "
                f"{type_instruction}"
            )
        
        # If we have allowed types, append a compact type constraint.
        if allowed_types and "Allowed t values:" not in extraction_prompt:
            extraction_prompt += f"\nAllowed t values: {', '.join(allowed_types)}"

        extraction_model_preset_id = (
            selected_prompt.get("model_preset_id") if isinstance(selected_prompt, dict) else None
        )
        extraction_max_tokens = (
            selected_prompt.get("max_tokens")
            if isinstance(selected_prompt, dict) and selected_prompt.get("max_tokens") is not None
            else extraction_config.get("max_tokens")
        )
        if extraction_max_tokens is not None:
            try:
                extraction_max_tokens = int(extraction_max_tokens)
            except (TypeError, ValueError):
                extraction_max_tokens = None

        extraction_preset = None
        if extraction_model_preset_id:
            extraction_preset = session.get(ModelPreset, extraction_model_preset_id)
            if extraction_preset is None:
                logger.warning(
                    "Extraction prompt preset %s not found; falling back to task defaults",
                    extraction_model_preset_id,
                )

        resolved_provider = extraction_config.get("provider", config.get("provider"))
        resolved_model = extraction_config.get("model")
        resolved_temperature = extraction_config.get("temperature", 0.3)
        resolved_thinking_mode = None
        if extraction_preset is not None:
            resolved_provider = extraction_preset.provider
            resolved_model = extraction_preset.model_id
            resolved_temperature = extraction_preset.temperature
            resolved_thinking_mode = extraction_preset.thinking_mode

        # Get LLM model
        llm = get_llm_model(
            task_name="extraction",
            provider=resolved_provider,
            model=resolved_model,
            temperature=resolved_temperature,
            max_tokens=extraction_max_tokens,
            thinking_mode=resolved_thinking_mode,
            use_flex=use_flex,
        )

        # Build paragraph list from edited markdown payload.
        edited_markdown = edited_transcript_markdown(lesson.edited_transcript)
        paragraph_texts = markdown_to_paragraphs(edited_markdown)
        if not paragraph_texts:
            logger.error(f"Lesson {lesson_id} has empty edited markdown to extract sources from")
            return False

        # Group paragraphs by word count
        words_per_group = extraction_config.get("words_per_group", DEFAULT_WORDS_PER_GROUP)
        paragraph_inputs: List[EditedParagraphInput] = []
        for idx, text in enumerate(paragraph_texts):
            paragraph_inputs.append(
                EditedParagraphInput(paragraph_number=idx, text=text)
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
            f"Extracting sources from lesson {lesson_id}: {len(paragraph_texts)} edited paragraphs "
            f"in {len(paragraph_groups)} groups (~{words_per_group} words/group) "
            f"with max concurrency {max_concurrency}"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(group):
            async with semaphore:
                return await extract_sources_from_paragraphs_with_retry(
                    group, llm, extraction_prompt, SourceOutputModel
                )

        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in paragraph_groups]
        results = await asyncio.gather(*tasks)

        # Delete existing sources for this lesson before re-extracting
        crud.delete_lesson_sources(session, lesson_id)

        # Build lesson_source rows from LLM results
        total_sources = 0
        for group_sources in results:
            for src in group_sources:
                if src.paragraph_number < 0 or src.paragraph_number >= len(paragraph_texts):
                    logger.warning(
                        "Skipping source with invalid paragraph_number %s",
                        src.paragraph_number,
                    )
                    continue
                crud.create_lesson_source(
                    session,
                    lesson_id=lesson_id,
                    paragraph_index=src.paragraph_number,
                    type=str(src.type) if src.type is not None else None,
                    work=src.work,
                    ref=src.ref,
                    standard_slug=src.standard_slug,
                    original_text=src.original_text,
                    translation_text=src.translation_text,
                    cited_excerpt=src.cited_excerpt,
                    confidence=src.confidence,
                )
                total_sources += 1

        # Save extraction metadata
        metadata = Metadata(
            provider=resolved_provider,
            model=resolved_model,
            temperature=resolved_temperature,
            max_tokens=extraction_max_tokens,
            prompt=extraction_prompt,
        )
        lesson.set_edited_metadata(metadata)

        # Commit changes
        session.add(lesson)
        session.commit()

        logger.info(
            f"Successfully extracted sources from lesson {lesson_id}: "
            f"{total_sources} sources found across {len(paragraph_texts)} edited paragraphs"
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
    prompt_type: Optional[str] = None,
    use_flex: bool = False,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for extract_sources_async.

    Args:
        lesson_id: ID of the lesson
        max_concurrency: Maximum number of concurrent LLM calls
        prompt_type: Name of the prompt to use from the prompts list
        session: Optional SQLModel session

    Returns:
        True if extraction was successful, False otherwise
    """
    return asyncio.run(
        extract_sources_async(
            lesson_id=lesson_id,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )
    )
