"""Lesson transcript correction using LLM"""
import asyncio
import json
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
from services.glossary_apply import (
    apply_glossary_to_segments_with_report,
    load_glossary_rules,
)
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds

COMPACT_CORRECTION_OUTPUT_INSTRUCTIONS = (
    "Return only corrected segments in this compact format: one changed segment "
    "per line as <id>|<corrected text>. Omit unchanged segments. If no segment "
    "needs correction, return exactly NONE. Do not return JSON, Markdown, code "
    "fences, explanations, or unchanged segments."
)


def _segment_text(segment: Segment) -> str:
    text = segment["text"] if isinstance(segment, dict) else segment.text
    return text or ""


def _response_text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return str(content or "").strip()


def _parse_legacy_json_corrections(output: str, group_size: int) -> dict[int, str]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {}

    if isinstance(payload, dict):
        rows = payload.get("segments", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        return {}

    corrections: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            segment_id = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        corrected_text = str(row.get("text") or "").strip()
        if 1 <= segment_id <= group_size and corrected_text:
            corrections[segment_id] = corrected_text
    return corrections


def _parse_compact_corrections(output: str, group_size: int) -> dict[int, str]:
    stripped_output = output.strip()
    if not stripped_output or stripped_output.upper() == "NONE":
        return {}

    legacy_corrections = _parse_legacy_json_corrections(stripped_output, group_size)
    if legacy_corrections:
        return legacy_corrections

    corrections: dict[int, str] = {}
    for raw_line in stripped_output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```") or line.upper() == "NONE":
            continue
        if "|" not in line:
            logger.warning("Ignoring unparsable correction line: %s", line[:120])
            continue

        id_part, corrected_text = line.split("|", 1)
        id_part = id_part.strip().lstrip("-*").strip()
        if id_part.endswith("."):
            id_part = id_part[:-1].strip()
        if not id_part.isdigit():
            logger.warning("Ignoring correction with invalid segment id: %s", line[:120])
            continue

        segment_id = int(id_part)
        corrected_text = corrected_text.strip()
        if not 1 <= segment_id <= group_size:
            logger.warning("Ignoring correction id outside group range: %s", segment_id)
            continue
        if corrected_text:
            corrections[segment_id] = corrected_text
    return corrections


async def correct_segment_group_with_retry(
    group: List[tuple[int, Segment]],
    llm,
    correction_prompt: str,
    max_retries: int = MAX_RETRIES
) -> List[tuple[int, str]]:
    """
    Correct a group of segments with retry logic for rate limits.
    
    Args:
        group: List of tuples (original_index, Segment or dict)
        llm: LLM model
        correction_prompt: Prompt for correction
        max_retries: Maximum number of retry attempts
        
    Returns:
        List of tuples (original_index, corrected_text)
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await correct_segment_group(group, llm, correction_prompt)
        
        except Exception as e:
            last_error = e
            error_message = str(e).lower()
            
            # Check if it's a rate limit error
            is_rate_limit = (
                'rate limit' in error_message or 
                'rate_limit' in error_message or
                '429' in error_message or
                'too many requests' in error_message or
                'quota' in error_message
            )
            
            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff with jitter
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
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


async def correct_segment_group(
    group: List[tuple[int, Segment]],
    llm,
    correction_prompt: str
) -> List[tuple[int, str]]:
    """
    Correct a group of segments using the LLM.
    
    Args:
        group: List of tuples (original_index, Segment or dict)
        llm: LLM model
        correction_prompt: Prompt for correction
        
    Returns:
        List of tuples (original_index, corrected_text)
    """
    try:
        # Create the prompt with the segments (numbered 1, 2, 3, ...)
        segments_text = "\n".join(
            f"{i + 1}. {_segment_text(segment)}"
            for i, (_, segment) in enumerate(group)
        )
        
        full_prompt = (
            f"{correction_prompt}\n\n"
            f"{COMPACT_CORRECTION_OUTPUT_INSTRUCTIONS}\n\n"
            f"Segments to review:\n{segments_text}"
        )
        
        # Call LLM with compact text output.
        response = await llm.ainvoke(full_prompt)
        output = _response_text(response)
        corrections_by_id = _parse_compact_corrections(output, len(group))
        # Map corrected segments back to original indices
        # Note: LLM only returns segments that need correction
        # Segments not in the response don't need correction and use original text
        corrected = []
        corrected_count = 0
        
        for i, (original_idx, segment) in enumerate(group):
            # Find the corrected segment by id (1-based)
            corrected_text = corrections_by_id.get(i + 1)
            if corrected_text is not None:
                # Use corrected text from LLM
                corrected.append((original_idx, corrected_text))
                corrected_count += 1
            else:
                # Segment not returned by LLM = doesn't need correction, use original
                corrected.append((original_idx, _segment_text(segment)))
        
        # Log correction statistics
        logger.info(
            f"Processed group: {corrected_count}/{len(group)} segments corrected, "
            f"{len(group) - corrected_count} kept original"
        )
        
        return corrected
    
    except Exception as e:
        logger.error(f"Error correcting segment group: {e}", exc_info=True)
        # Return original texts on error
        result = []
        for original_idx, segment in group:
            result.append((original_idx, _segment_text(segment)))
        return result


async def correct_transcript_async(
    lesson_id: int,
    segments_per_group: int = 100,
    max_concurrency: int = 10,
    prompt_type: Optional[str] = None,
    use_flex: bool = False,
    session: Optional[Session] = None,
) -> bool:
    """
    Correct a lesson transcript by processing segments in parallel groups.
    
    Args:
        lesson_id: ID of the lesson to correct
        segments_per_group: Number of segments to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session (will create one if not provided)
        
    Returns:
        True if correction was successful, False otherwise
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
        
        if not lesson.transcript:
            logger.error(f"Lesson {lesson_id} has no transcript to correct")
            return False
        
        # Load config
        config = load_config()
        correction_config = config.get('correction', {})

        # Resolve prompt from prompts list (like summary) with backward compat
        prompts = correction_config.get('prompts', [])
        if not prompts and 'prompt' in correction_config:
            prompts = [{'name': 'Default', 'text': correction_config['prompt']}]

        selected_prompt = None
        correction_prompt = None
        if prompt_type:
            for p in prompts:
                if p.get('name') == prompt_type:
                    selected_prompt = p
                    correction_prompt = p.get('text')
                    break

        if not correction_prompt and prompts:
            selected_prompt = prompts[0]
            correction_prompt = prompts[0].get('text')

        if not correction_prompt:
            correction_prompt = 'Please correct the following transcript, fixing any errors while maintaining the original meaning and style.'
        
        correction_prompt_max_tokens = (
            selected_prompt.get("max_tokens", 16000)
            if isinstance(selected_prompt, dict)
            else correction_config.get("max_tokens", 16000)
        )
        try:
            correction_prompt_max_tokens = int(correction_prompt_max_tokens)
        except (TypeError, ValueError):
            correction_prompt_max_tokens = 16000
        correction_prompt_max_tokens = max(1, correction_prompt_max_tokens)

        correction_model_preset = None
        correction_model_preset_id = (
            selected_prompt.get("model_preset_id")
            if isinstance(selected_prompt, dict)
            else None
        )
        if correction_model_preset_id is not None:
            try:
                correction_model_preset = session.get(ModelPreset, int(correction_model_preset_id))
            except (TypeError, ValueError):
                correction_model_preset = None
            if not correction_model_preset:
                logger.warning(
                    "Correction prompt '%s' references missing model preset id=%s; using fallback config.",
                    selected_prompt.get("name") if isinstance(selected_prompt, dict) else None,
                    correction_model_preset_id,
                )

        # Get LLM model
        if correction_model_preset:
            llm = get_llm_model(
                provider=correction_model_preset.provider,
                model=correction_model_preset.model_id,
                temperature=correction_model_preset.temperature,
                max_tokens=correction_prompt_max_tokens,
                thinking_mode=correction_model_preset.thinking_mode or None,
                use_flex=use_flex,
            )
        else:
            llm = get_llm_model(
                task_name='correction',
                max_tokens=correction_prompt_max_tokens,
                use_flex=use_flex,
            )
        
        # Split segments into groups
        segments = lesson.transcript
        segment_groups = []
        
        for i in range(0, len(segments), segments_per_group):
            group = list(enumerate(segments[i:i + segments_per_group], start=i))
            segment_groups.append(group)
        
        logger.info(
            f"Correcting lesson {lesson_id}: {len(segments)} segments "
            f"in {len(segment_groups)} groups with max concurrency {max_concurrency}"
        )
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def process_with_semaphore(group):
            async with semaphore:
                return await correct_segment_group_with_retry(
                    group, llm, correction_prompt
                )
        
        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in segment_groups]
        results = await asyncio.gather(*tasks)
        
        # Flatten results and sort by original index
        all_corrections = []
        for group_result in results:
            all_corrections.extend(group_result)
        
        all_corrections.sort(key=lambda x: x[0])
        
        # Update segments with corrected text
        corrected_segments = []
        for i, (idx, corrected_text) in enumerate(all_corrections):
            if idx < len(segments):
                original_segment = segments[idx]
                # Handle both dict and Segment objects
                if isinstance(original_segment, dict):
                    corrected_segment = Segment(
                        start=original_segment['start'],
                        end=original_segment['end'],
                        text=corrected_text
                    )
                else:
                    corrected_segment = Segment(
                        start=original_segment.start,
                        end=original_segment.end,
                        text=corrected_text
                    )
                corrected_segments.append(corrected_segment)
        
        corrected_data = [seg.model_dump() for seg in corrected_segments]
        glossary_rules = load_glossary_rules(session)
        corrected_data, glossary_report = apply_glossary_to_segments_with_report(
            corrected_data, glossary_rules
        )
        
        # Save correction metadata
        correction_provider = (
            correction_model_preset.provider
            if correction_model_preset
            else correction_config.get("provider", config.get("provider"))
        )
        metadata = Metadata(
            provider=correction_provider,
            model=(
                correction_model_preset.model_id
                if correction_model_preset
                else correction_config.get('model')
            ),
            temperature=(
                correction_model_preset.temperature
                if correction_model_preset
                else correction_config.get('temperature')
            ),
            max_tokens=correction_prompt_max_tokens,
            prompt=correction_prompt,
        )
        lesson.set_correction_metadata(metadata)
        if lesson.correction_metadata is None:
            lesson.correction_metadata = {}
        lesson.correction_metadata["glossary_replacements"] = glossary_report
        
        # Commit metadata and versioned content in the same job.
        session.add(lesson)
        session.commit()
        update_content(
            session=session,
            lesson_id=lesson_id,
            content_type=ContentType.CORRECTED_TRANSCRIPT,
            new_content=corrected_data,
            actor=None,
            source=VersionSource.PIPELINE,
            change_summary="Pipeline correction rerun",
        )
        session.commit()
        
        logger.info(f"Successfully corrected lesson {lesson_id} transcript")
        return True
    
    except Exception as e:
        logger.error(f"Error correcting lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False
    
    finally:
        if should_close_session and session:
            session.close()


def correct_transcript(
    lesson_id: int,
    segments_per_group: int = 10,
    max_concurrency: int = 10,
    prompt_type: Optional[str] = None,
    use_flex: bool = False,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for correct_transcript_async.
    
    Args:
        lesson_id: ID of the lesson to correct
        segments_per_group: Number of segments to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        prompt_type: Name of the prompt to use from the prompts list
        session: Optional SQLModel session
        
    Returns:
        True if correction was successful, False otherwise
    """
    return asyncio.run(
        correct_transcript_async(
            lesson_id=lesson_id,
            segments_per_group=segments_per_group,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )
    )

