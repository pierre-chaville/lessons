"""Source verification using Sefaria API and LLM"""

import asyncio
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlmodel import Session
import sys
from pathlib import Path
import httpx
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson, Source
from config import load_config
from .llm_utils import get_llm_model

logger = logging.getLogger(__name__)

# Sefaria API base URL
SEFARIA_API_BASE = "https://www.sefaria.org/api/texts"

# Concurrency limit for parallel processing
MAX_CONCURRENCY = 10


class SourceVerificationOutput(BaseModel):
    """Structured output for source verification"""

    citation_found: bool = Field(
        description="Whether the citation was found in the source text"
    )
    confidence: float = Field(
        description="Confidence score between 0 and 1 [1 = high confidence, 0 = low confidence]"
    )
    explanation: str = Field(
        description="Explanation of why the citation was found or not found (in french)"
    )
    matched_text: Optional[str] = Field(
        default=None,
        description="The actual text from the source that matches the citation, if found"
    )


async def fetch_sefaria_text(slug: str) -> Optional[Dict[str, Any]]:
    """
    Fetch text from Sefaria API using the slug.

    Args:
        slug: Sefaria slug (e.g., "Pirkei_Avot.4.2")

    Returns:
        Dictionary with text data from Sefaria API, or None if fetch failed
    """
    try:
        url = f"{SEFARIA_API_BASE}/{slug}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch Sefaria text for slug {slug}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching Sefaria text for slug {slug}: {e}")
        return None


def extract_text_from_sefaria_response(sefaria_data: Dict[str, Any]) -> str:
    """
    Extract the text content from Sefaria API response.

    Args:
        sefaria_data: JSON response from Sefaria API

    Returns:
        Extracted text as a string
    """
    try:
        # Sefaria API returns text in different formats depending on the source
        # Common structure: {"text": [...]} or {"he": "...", "text": [...]}
        if "text" in sefaria_data:
            text_data = sefaria_data["text"]
            if isinstance(text_data, list):
                # Flatten list of strings/paragraphs
                return "\n".join(
                    item if isinstance(item, str) else " ".join(item)
                    for item in text_data
                )
            elif isinstance(text_data, str):
                return text_data
        # Fallback: try to get Hebrew text
        if "he" in sefaria_data:
            return sefaria_data["he"]
        # Last resort: convert entire response to string
        return str(sefaria_data)
    except Exception as e:
        logger.error(f"Error extracting text from Sefaria response: {e}")
        return ""


async def verify_source_with_llm(
    source: Source, sefaria_text: str, sources_prompt: str, llm_with_structure
) -> SourceVerificationOutput:
    """
    Verify a source citation using LLM with structured output.

    Args:
        source: Source object to verify
        sefaria_text: Text retrieved from Sefaria API
        sources_prompt: Prompt template for source verification
        llm_with_structure: LLM model with structured output capability

    Returns:
        SourceVerificationOutput with verification results
    """
    try:
        # Build the prompt with source information and Sefaria text
        original_text = source.original_text if source.original_text else 'Not provided'
        translation_text = source.translation_text if source.translation_text else 'Not provided'
        source_type = source.type if source.type else 'Unknown'
        work = source.work if source.work else 'Unknown'
        ref = source.ref if source.ref else 'Unknown'
        slug = source.standard_slug if source.standard_slug else 'Unknown'
        
        prompt = f"""{sources_prompt}

Source Information:
- Type: {source_type}
- Work: {work}
- Reference: {ref}
- Slug: {slug}
- Original Text (claimed): {original_text}
- Translation Text (claimed): {translation_text}

Text from Sefaria API (slug: {slug}):
{sefaria_text}

Please verify if the claimed citation matches the text from Sefaria. Check if the original_text or translation_text appears in the Sefaria text, and provide your assessment."""

        # Call LLM with structured output
        result = await llm_with_structure.ainvoke(prompt)
        return result

    except Exception as e:
        logger.error(f"Error verifying source with LLM: {e}")
        # Return default negative result on error
        return SourceVerificationOutput(
            citation_found=False,
            confidence=0.0,
            explanation=f"Error during verification: {str(e)}",
            matched_text=None,
        )


async def verify_single_source(
    source: Source, sources_config: Dict[str, Any]
) -> Source:
    """
    Verify a single source by fetching from Sefaria and checking with LLM.

    Args:
        source: Source object to verify (can be dict or Source instance)
        sources_config: Configuration dictionary for sources task

    Returns:
        Updated Source object with verification results
    """
    # Convert dict to Source if needed
    if isinstance(source, dict):
        source = Source(**source)
    
    # Initialize verification fields
    source.slug_retrieved = False
    source.citation_found = False
    source.verification_confidence = None
    source.verification_explanation = None
    source.matched_text = None

    # Check if slug is available
    if not source.standard_slug:
        source.verification_explanation = "No standard_slug provided for verification"
        return source

    # Fetch text from Sefaria API
    sefaria_data = await fetch_sefaria_text(source.standard_slug)

    if sefaria_data is None:
        source.verification_explanation = (
            f"Failed to retrieve text from Sefaria API for slug: {source.standard_slug}"
        )
        return source

    # Mark that slug was retrieved successfully
    source.slug_retrieved = True

    # Extract text from Sefaria response
    sefaria_text = extract_text_from_sefaria_response(sefaria_data)

    if not sefaria_text:
        source.verification_explanation = (
            f"Retrieved Sefaria data but could not extract text for slug: {source.standard_slug}"
        )
        return source

    # Get LLM model and prompt from config
    model = sources_config.get("model", "gpt-4o")
    temperature = sources_config.get("temperature", 0.3)
    prompt = sources_config.get("prompt", "")

    if not prompt:
        source.verification_explanation = "No prompt configured for source verification"
        return source

    # Get LLM model with structured output
    llm = get_llm_model(task_name="sources", temperature=temperature, model=model)
    llm_with_structure = llm.with_structured_output(SourceVerificationOutput)

    # Verify with LLM
    verification_result = await verify_source_with_llm(
        source, sefaria_text, prompt, llm_with_structure
    )

    # Update source with verification results
    source.citation_found = verification_result.citation_found
    source.verification_confidence = verification_result.confidence
    source.verification_explanation = verification_result.explanation
    source.matched_text = verification_result.matched_text

    return source


async def verify_sources_async(
    sources: List[Source],
    session: Optional[Session] = None,
) -> List[Source]:
    """
    Verify multiple sources in parallel with concurrency limit.

    Args:
        sources: List of Source objects to verify
        session: Optional SQLModel session (not used but kept for consistency)

    Returns:
        List of updated Source objects with verification results
    """
    # Load sources configuration
    config = load_config()
    sources_config = config.get("sources", {})

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def verify_with_semaphore(source: Source) -> Source:
        async with semaphore:
            return await verify_single_source(source, sources_config)

    # Process all sources in parallel (with concurrency limit)
    logger.info(f"Verifying {len(sources)} sources with max concurrency {MAX_CONCURRENCY}")
    results = await asyncio.gather(*[verify_with_semaphore(source) for source in sources])

    logger.info(
        f"Completed verification of {len(sources)} sources. "
        f"Retrieved: {sum(1 for s in results if s.slug_retrieved)}, "
        f"Found: {sum(1 for s in results if s.citation_found)}"
    )

    return results


def verify_sources(
    sources: List[Source],
    session: Optional[Session] = None,
) -> List[Source]:
    """
    Synchronous wrapper for verify_sources_async.

    Args:
        sources: List of Source objects to verify
        session: Optional SQLModel session

    Returns:
        List of updated Source objects with verification results
    """
    return asyncio.run(verify_sources_async(sources, session=session))


async def verify_lesson_sources_async(
    lesson_id: int,
    session: Optional[Session] = None,
) -> bool:
    """
    Verify all sources in a lesson's edited transcript.

    Args:
        lesson_id: ID of the lesson to verify sources for
        session: Optional SQLModel session (will create one if not provided)

    Returns:
        True if verification was successful, False otherwise
    """
    should_close_session = False

    try:
        # Create session if not provided
        if session is None:
            session = Session(engine)
            should_close_session = True

        # Load lesson
        from models import Lesson
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return False

        if not lesson.edited_transcript:
            logger.error(f"Lesson {lesson_id} has no edited transcript")
            return False

        # Collect all sources from edited transcript
        # Note: edited_transcript is stored as JSON, so sources are dicts
        all_sources = []
        for part_dict in lesson.edited_transcript:
            if isinstance(part_dict, dict) and part_dict.get("sources"):
                for source_dict in part_dict["sources"]:
                    all_sources.append(Source(**source_dict))
            elif hasattr(part_dict, "sources") and part_dict.sources:
                for source in part_dict.sources:
                    if isinstance(source, dict):
                        all_sources.append(Source(**source))
                    else:
                        all_sources.append(source)

        if not all_sources:
            logger.info(f"Lesson {lesson_id} has no sources to verify")
            return True

        # Verify sources
        verified_sources = await verify_sources_async(all_sources, session)

        # Update sources in edited transcript
        source_index = 0
        updated_parts = []
        for part_dict in lesson.edited_transcript:
            if isinstance(part_dict, dict):
                # Handle dict format (from JSON storage)
                part = part_dict.copy()
                if part.get("sources"):
                    updated_sources = []
                    for i in range(len(part["sources"])):
                        updated_sources.append(verified_sources[source_index].model_dump())
                        source_index += 1
                    part["sources"] = updated_sources
                updated_parts.append(part)
            else:
                # Handle object format
                part = part_dict
                if hasattr(part, "sources") and part.sources:
                    updated_sources = []
                    for i in range(len(part.sources)):
                        updated_sources.append(verified_sources[source_index].model_dump())
                        source_index += 1
                    part.sources = updated_sources
                updated_parts.append(part.model_dump() if hasattr(part, "model_dump") else part)

        # Update lesson with verified sources
        lesson.edited_transcript = updated_parts

        # Commit changes
        session.add(lesson)
        session.commit()

        logger.info(
            f"Successfully verified {len(verified_sources)} sources for lesson {lesson_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error verifying sources for lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False

    finally:
        if should_close_session and session:
            session.close()


def verify_lesson_sources(
    lesson_id: int,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for verify_lesson_sources_async.

    Args:
        lesson_id: ID of the lesson to verify sources for
        session: Optional SQLModel session

    Returns:
        True if verification was successful, False otherwise
    """
    return asyncio.run(verify_lesson_sources_async(lesson_id, session=session))
