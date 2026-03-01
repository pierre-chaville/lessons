"""Source verification using Sefaria API and LLM"""

import asyncio
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from sqlmodel import Session
import sys
from pathlib import Path
import httpx
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson
from models.sefaria_cache import SefariaCache
from schemas import Source
from config import load_config
from .llm_utils import get_llm_model
import crud

logger = logging.getLogger(__name__)

# Sefaria API base URL
SEFARIA_API_BASE = "https://www.sefaria.org/api/texts"

# Concurrency limit for parallel processing
MAX_CONCURRENCY = 10


class VerificationStatus(str, Enum):
    """Status of citation verification"""
    
    FOUND = "exactly_found"
    SIMILAR = "paraphrase_or_similar"
    PARTIAL = "partially_found"
    NOT_FOUND = "not_found"
    WRONG_REF = "reference_exists_but_text_differs"


class SourceVerificationOutput(BaseModel):
    """Structured output for source verification"""

    verification_status: VerificationStatus = Field(
        description="Verification status: exactly_found, paraphrase_or_similar, partially_found, not_found, or reference_exists_but_text_differs"
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


def _flatten_text(data) -> str:
    """Flatten a Sefaria text field (string, list of strings, or nested list) to a single string."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return "\n".join(
            item.replace("\n", " ") if isinstance(item, str) else " ".join(item) if isinstance(item, list) else str(item).replace("\n", " ")
            for item in data
        )
    return str(data)


def extract_text_from_sefaria_response(sefaria_data: Dict[str, Any]) -> str:
    """
    Extract the English text content from Sefaria API response.

    Args:
        sefaria_data: JSON response from Sefaria API

    Returns:
        Extracted text as a string
    """
    try:
        if "text" in sefaria_data:
            return _flatten_text(sefaria_data["text"])
        if "he" in sefaria_data:
            return _flatten_text(sefaria_data["he"])
        return str(sefaria_data)
    except Exception as e:
        logger.error(f"Error extracting text from Sefaria response: {e}")
        return ""


def extract_hebrew_text_from_sefaria_response(sefaria_data: Dict[str, Any]) -> str:
    """
    Extract the Hebrew text content from Sefaria API response.

    Args:
        sefaria_data: JSON response from Sefaria API

    Returns:
        Hebrew text as a string, or empty string if not available
    """
    try:
        if "he" in sefaria_data:
            return _flatten_text(sefaria_data["he"])
        return ""
    except Exception as e:
        logger.error(f"Error extracting Hebrew text from Sefaria response: {e}")
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

Please verify if the claimed citation matches the text from Sefaria. Check if the original_text or translation_text appears in the Sefaria text, and provide your assessment.

Return verification_status as one of:
- exactly_found: The citation matches exactly
- paraphrase_or_similar: The citation is a paraphrase or similar wording
- partially_found: Only part of the citation is found
- not_found: The citation is not found in the source
- reference_exists_but_text_differs: The reference exists but the text is different"""

        # Call LLM with structured output
        result = await llm_with_structure.ainvoke(prompt)
        return result

    except Exception as e:
        logger.error(f"Error verifying source with LLM: {e}")
        # Return default negative result on error
        return SourceVerificationOutput(
            verification_status=VerificationStatus.NOT_FOUND,
            confidence=0.0,
            explanation=f"Error during verification: {str(e)}",
            matched_text=None,
        )


async def verify_single_source(
    source: Source,
    sources_config: Dict[str, Any],
    prefetched_text: Optional[str] = None,
) -> Source:
    """
    Verify a single source using pre-fetched Sefaria text and LLM.

    Args:
        source: Source object to verify (can be dict or Source instance)
        sources_config: Configuration dictionary for sources task
        prefetched_text: Pre-fetched Sefaria text (from cache or API). None means
                         the slug was not found / not available.

    Returns:
        Updated Source object with verification results
    """
    # Convert dict to Source if needed
    if isinstance(source, dict):
        source = Source(**source)
    
    # Initialize verification fields
    source.slug_retrieved = False
    source.verification_status = None
    source.verification_confidence = None
    source.verification_explanation = None
    source.matched_text = None

    # Check if slug is available
    if not source.standard_slug:
        source.verification_explanation = "No standard_slug provided for verification"
        return source

    # Check if we have text to verify against
    if prefetched_text is None:
        source.verification_explanation = (
            f"Failed to retrieve text from Sefaria API for slug: {source.standard_slug}"
        )
        return source

    if not prefetched_text:
        source.verification_explanation = (
            f"Retrieved Sefaria data but could not extract text for slug: {source.standard_slug}"
        )
        return source

    # Mark that slug was retrieved successfully
    source.slug_retrieved = True

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
        source, prefetched_text, prompt, llm_with_structure
    )

    # Update source with verification results
    source.verification_status = verification_result.verification_status.value
    source.verification_confidence = verification_result.confidence
    source.verification_explanation = verification_result.explanation
    source.matched_text = verification_result.matched_text

    return source


async def _prefetch_sefaria_texts(
    sources: List[Source],
    db_session: Session,
) -> Dict[str, Optional[str]]:
    """
    Pre-fetch all required Sefaria texts, using the cache first and calling the
    Sefaria API only for slugs that are missing from the cache.  Newly fetched
    texts are stored back in the cache for future use.

    Args:
        sources: List of Source objects whose slugs we need to resolve.
        db_session: Active SQLModel session for cache reads / writes.

    Returns:
        Mapping  slug → english_text  (value is None when the slug could not be
        resolved from either cache or API).
    """
    # 1. Collect unique slugs that need to be looked up
    slugs_needed: Dict[str, Source] = {}
    for src in sources:
        s = src if not isinstance(src, dict) else Source(**src)
        if s.standard_slug and s.standard_slug not in slugs_needed:
            slugs_needed[s.standard_slug] = s

    if not slugs_needed:
        return {}

    unique_slugs = list(slugs_needed.keys())
    logger.info(f"Sefaria prefetch: {len(unique_slugs)} unique slugs required")

    # 2. Batch-lookup cache
    cached_entries = crud.get_sefaria_cache_by_slugs(db_session, unique_slugs)
    cached_map: Dict[str, SefariaCache] = {e.standard_slug: e for e in cached_entries}

    slug_text_map: Dict[str, Optional[str]] = {}
    missing_slugs: List[str] = []

    for slug in unique_slugs:
        if slug in cached_map:
            entry = cached_map[slug]
            # Prefer English text, fallback to Hebrew
            text = entry.text_english or entry.text_hebrew or ""
            slug_text_map[slug] = text
        else:
            missing_slugs.append(slug)

    logger.info(
        f"Sefaria prefetch: {len(cached_map)} found in cache, "
        f"{len(missing_slugs)} need API call"
    )

    # 3. Fetch missing slugs from Sefaria API (in parallel with concurrency control)
    if missing_slugs:
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def _fetch_one(slug: str) -> tuple:
            async with semaphore:
                data = await fetch_sefaria_text(slug)
                return slug, data

        api_results = await asyncio.gather(*[_fetch_one(s) for s in missing_slugs])

        for slug, data in api_results:
            if data is None:
                slug_text_map[slug] = None
                continue

            en_text = extract_text_from_sefaria_response(data)
            he_text = extract_hebrew_text_from_sefaria_response(data)

            slug_text_map[slug] = en_text or he_text or ""

            # 4. Store in cache (only when we actually got something)
            if en_text or he_text:
                ref_source = slugs_needed.get(slug)
                try:
                    crud.upsert_sefaria_cache(
                        db_session,
                        standard_slug=slug,
                        type=ref_source.type if ref_source else None,
                        work=ref_source.work if ref_source else None,
                        ref=ref_source.ref if ref_source else None,
                        he_ref=data.get("heRef"),
                        text_english=en_text or None,
                        text_hebrew=he_text or None,
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache Sefaria text for {slug}: {e}")

        logger.info(
            f"Sefaria prefetch: fetched {sum(1 for _, d in api_results if d is not None)} "
            f"of {len(missing_slugs)} from API"
        )

    return slug_text_map


async def verify_sources_async(
    sources: List[Source],
    session: Optional[Session] = None,
) -> List[Source]:
    """
    Verify multiple sources in parallel with concurrency limit.
    Uses sefaria_cache to avoid redundant API calls: texts are looked up in
    cache first, only missing slugs are fetched from Sefaria and stored back.

    Args:
        sources: List of Source objects to verify
        session: Optional SQLModel session

    Returns:
        List of updated Source objects with verification results
    """
    # Load sources configuration
    config = load_config()
    sources_config = config.get("sources", {})

    # Open a DB session for cache operations
    should_close = False
    if session is None:
        session = Session(engine)
        should_close = True

    try:
        # --- Phase 1: Pre-fetch all Sefaria texts (cache + API) ---
        slug_text_map = await _prefetch_sefaria_texts(sources, session)

        # --- Phase 2: Run LLM verification in parallel ---
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def verify_with_semaphore(source: Source) -> Source:
            async with semaphore:
                s = source if not isinstance(source, dict) else Source(**source)
                text = slug_text_map.get(s.standard_slug) if s.standard_slug else None
                return await verify_single_source(s, sources_config, prefetched_text=text)

        logger.info(
            f"Verifying {len(sources)} sources with max concurrency {MAX_CONCURRENCY}"
        )
        results = await asyncio.gather(
            *[verify_with_semaphore(source) for source in sources]
        )

        logger.info(
            f"Completed verification of {len(sources)} sources. "
            f"Retrieved: {sum(1 for s in results if s.slug_retrieved)}, "
            f"Found: {sum(1 for s in results if s.verification_status and s.verification_status in [VerificationStatus.FOUND.value, VerificationStatus.SIMILAR.value, VerificationStatus.PARTIAL.value])}"
        )

        return results
    finally:
        if should_close:
            session.close()


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
