"""Lesson transcript edition using LLM - rewrite in written style with sources"""

import asyncio
import json
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session
import sys
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import engine
from models import Lesson, Segment, EditedPart, Source, Metadata
from config import load_config
from .llm_utils import get_llm_model
import logging

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 60  # seconds


# Input/Output models for structured output
class SegmentInput(BaseModel):
    """Input segment with timing for edition"""

    segment_number: int = Field(description="Segment number (0-indexed or 1-indexed, consistent within a group)")
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    text: str = Field(description="Original transcript text")


class EditedPartOutput(BaseModel):
    """Output: Edited paragraph with segment numbers"""

    start_segment: int = Field(
        description="Starting segment number (INCLUSIVE, 0-indexed within the group). "
        "This segment IS included in this edited part."
    )
    end_segment: int = Field(
        description="Ending segment number (INCLUSIVE, 0-indexed within the group). "
        "This segment IS included in this edited part. Must be >= start_segment."
    )
    text: str = Field(description="Rewritten text as a paragraph in clear, written style")


class TranscriptGroupInput(BaseModel):
    """Input: Group of segments to edit"""

    segments: List[SegmentInput] = Field(description="List of transcript segments")


class EditedTranscriptGroupOutput(BaseModel):
    """Output: Group of edited paragraphs"""

    parts: List[EditedPartOutput] = Field(
        description="List of edited paragraphs (can combine multiple segments into one paragraph)"
    )


async def edit_segment_group_with_retry(
    group: List[Segment],
    llm_with_structure,
    edition_prompt: str,
    llm_fallback=None,
    max_retries: int = MAX_RETRIES,
) -> List[EditedPartOutput]:
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
                group, llm_with_structure, edition_prompt, llm_fallback
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
                        llm_with_structure,
                        edition_prompt,
                        llm_fallback=llm_fallback,
                        max_retries=max_retries,
                    )
                    second = await edit_segment_group_with_retry(
                        group[mid:],
                        llm_with_structure,
                        edition_prompt,
                        llm_fallback=llm_fallback,
                        max_retries=max_retries,
                    )
                    return first + second

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


def _extract_json_from_text(text: str) -> Optional[Any]:
    """Extract JSON object from LLM output."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_structured_result(result: Any) -> Optional[EditedTranscriptGroupOutput]:
    """Coerce structured output or tool calls into a validated output model."""
    if result is None:
        return None

    if isinstance(result, EditedTranscriptGroupOutput):
        return result

    if isinstance(result, dict):
        parsed = result.get("parsed")
        if isinstance(parsed, EditedTranscriptGroupOutput):
            return parsed
        if isinstance(parsed, dict):
            return EditedTranscriptGroupOutput.model_validate(parsed)

        raw = result.get("raw")
        tool_calls = getattr(raw, "tool_calls", None) if raw else None
        if tool_calls:
            args = tool_calls[0].get("args")
            if isinstance(args, dict):
                return EditedTranscriptGroupOutput.model_validate(args)
            if isinstance(args, str):
                parsed_args = _extract_json_from_text(args)
                if parsed_args is not None:
                    return EditedTranscriptGroupOutput.model_validate(parsed_args)

    return None


async def edit_segment_group(
    group: List[Segment],
    llm_with_structure,
    edition_prompt: str,
    llm_fallback=None,
) -> List[EditedPartOutput]:
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
        # Prepare input data - handle both Segment objects and dicts
        # Include segment numbers (0-indexed within the group)
        input_segments = []
        for idx, segment in enumerate(group):
            if isinstance(segment, dict):
                input_segments.append(
                    SegmentInput(
                        segment_number=idx,
                        start=segment["start"],
                        end=segment["end"],
                        text=segment["text"]
                    )
                )
            else:
                input_segments.append(
                    SegmentInput(
                        segment_number=idx,
                        start=segment.start,
                        end=segment.end,
                        text=segment.text
                    )
                )

        input_data = TranscriptGroupInput(segments=input_segments)

        # Create the prompt with the segments, including segment numbers
        segments_text = "\n".join(
            [
                f"Segment {seg.segment_number}: [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}"
                for seg in input_segments
            ]
        )

        # Add clear instructions about segment numbering
        num_segments = len(input_segments)
        segment_instructions = (
            f"\n\nIMPORTANT - Segment Numbering Rules:\n"
            f"- Segment numbers are 0-indexed (first segment is 0, last segment is {num_segments - 1})\n"
            f"- start_segment and end_segment are INCLUSIVE (both boundaries are included)\n"
            f"- You MUST cover ALL segments from 0 to {num_segments - 1} without gaps\n"
            f"- Each segment can only appear in ONE edited paragraph (no overlaps)\n"
            f"- Example: If you have segments 0-4, valid ranges are: [0,0], [1,2], [3,4] or [0,4] etc.\n"
        )

        full_prompt = (
            f"{edition_prompt}\n\n"
            f"Transcript to edit (use segment numbers for start_segment and end_segment):\n"
            f"{segments_text}"
            f"{segment_instructions}"
        )

        # Call LLM with structured output
        result = None
        structured_error = None
        try:
            result = await llm_with_structure.ainvoke(full_prompt)
        except Exception as e:
            structured_error = e

        structured_output = _coerce_structured_result(result)
        if structured_output is None or not structured_output.parts:
            if llm_fallback is None:
                raise structured_error or ValueError(
                    "Structured output missing 'parts'"
                )

            # Fallback: ask for plain JSON and parse manually
            fallback_prompt = (
                f"{full_prompt}\n\n"
                "Return ONLY valid JSON with this schema:\n"
                '{"parts":[{"start_segment":0,"end_segment":0,"text":"..."}]}'
            )
            raw = await llm_fallback.ainvoke(fallback_prompt)
            raw_text = raw.content if hasattr(raw, "content") else str(raw)
            parsed = _extract_json_from_text(raw_text)
            if parsed is None:
                raise ValueError("Failed to parse JSON from fallback response")
            try:
                structured_output = EditedTranscriptGroupOutput.model_validate(parsed)
            except ValidationError as e:
                raise ValueError(f"Invalid fallback JSON: {e}") from e
        result = structured_output

        # Validate that there are no gaps or overlaps in segment numbers and convert to timestamps
        used_segments = set()
        parts_with_timestamps = []
        
        for part_idx, part in enumerate(result.parts):
            # Validate segment range
            if part.start_segment < 0 or part.end_segment >= len(group):
                raise ValueError(
                    f"Invalid segment range in part {part_idx}: start_segment={part.start_segment}, "
                    f"end_segment={part.end_segment} (valid range: 0-{len(group)-1})"
                )
            if part.start_segment > part.end_segment:
                raise ValueError(
                    f"Invalid range in part {part_idx}: start_segment ({part.start_segment}) must be <= end_segment ({part.end_segment})"
                )
            
            # Check for overlaps (segments already used by another part)
            part_segments = set(range(part.start_segment, part.end_segment + 1))
            overlap = part_segments & used_segments
            if overlap:
                raise ValueError(
                    f"Overlap detected in part {part_idx}: segments {sorted(overlap)} are already covered by another part. "
                    f"This part covers segments {part.start_segment}-{part.end_segment}."
                )
            
            # Track used segments
            used_segments.update(part_segments)
            
            # Convert segment numbers to timestamps
            start_seg = input_segments[part.start_segment]
            end_seg = input_segments[part.end_segment]
            
            # Store timestamps separately (Pydantic models don't allow arbitrary attributes)
            # We'll return a tuple: (EditedPartOutput, start_time, end_time)
            parts_with_timestamps.append((part, start_seg.start, end_seg.end))
        
        # Check for gaps (missing segments)
        expected_segments = set(range(len(group)))
        missing_segments = expected_segments - used_segments
        if missing_segments:
            raise ValueError(
                f"Gap in segment coverage: segments {sorted(missing_segments)} are not covered by any edited part. "
                f"All segments from 0 to {len(group)-1} must be covered exactly once."
            )

        # Log statistics
        logger.info(
            f"Processed group: {len(group)} segments -> {len(parts_with_timestamps)} edited parts"
        )

        return parts_with_timestamps

    except Exception as e:
        logger.error(f"Error editing segment group: {e}", exc_info=True)
        # Return single part with original text concatenated on error
        # Cover all segments (0 to len(group)-1)
        start_time = group[0]["start"] if isinstance(group[0], dict) else group[0].start
        end_time = group[-1]["end"] if isinstance(group[-1], dict) else group[-1].end
        combined_text = " ".join(
            [seg["text"] if isinstance(seg, dict) else seg.text for seg in group]
        )

        part = EditedPartOutput(
            start_segment=0,
            end_segment=len(group) - 1,
            text=combined_text
        )
        # Return tuple with timestamps
        return [(part, start_time, end_time)]


async def edit_transcript_async(
    lesson_id: int,
    words_per_group: int = 1000,
    max_concurrency: int = 10,
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

        edition_prompt = edition_config.get(
            "prompt",
            "Please rewrite the following transcript in a clear, written style while maintaining the original meaning and flow. "
            "For each edited part, specify start_segment and end_segment (segment numbers, 0-indexed, INCLUSIVE boundaries) "
            "to indicate which segments are covered by that part. "
            "IMPORTANT: All segments must be covered exactly once without gaps or overlaps. "
            "Each segment number can only appear in one edited part. "
            "Focus only on rewriting the text - do not extract or mention sources.",
        )

        # Get LLM model
        llm = get_llm_model(task_name="edition")

        # Add structured output (include_raw helps recover tool calls for Anthropic)
        edition_provider = edition_config.get("provider", "")
        include_raw = edition_provider.lower() == "anthropic"
        llm_with_structure = llm.with_structured_output(
            EditedTranscriptGroupOutput, include_raw=include_raw
        )

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
                    group, llm_with_structure, edition_prompt, llm_fallback=llm
                )

        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in segment_groups]
        results = await asyncio.gather(*tasks)

        # Flatten results - each result is a list of tuples: (EditedPartOutput, start_time, end_time)
        all_edited_parts = []
        for group_result in results:
            all_edited_parts.extend(group_result)
        print(results)
        # Convert to EditedPart model objects (without sources - they will be extracted separately)
        edited_parts = []
        for part_tuple in all_edited_parts:
            # Unpack the tuple: (EditedPartOutput, start_time, end_time)
            part, start_time, end_time = part_tuple

            edited_parts.append(
                EditedPart(
                    start=start_time, end=end_time, text=part.text, sources=[]
                )
            )

        # Update lesson with edited transcript (convert to dicts for JSON storage)
        lesson.edited_transcript = [part.model_dump() for part in edited_parts]

        # Save edition metadata
        edition_provider = edition_config.get("provider", config.get("provider"))
        metadata = Metadata(
            provider=edition_provider,
            model=edition_config.get("model"),
            temperature=edition_config.get("temperature"),
            prompt=edition_prompt,
        )
        lesson.set_edited_metadata(metadata)

        # Commit changes
        session.add(lesson)
        session.commit()

        logger.info(
            f"Successfully edited lesson {lesson_id} transcript: "
            f"{len(segments)} segments -> {len(edited_parts)} edited parts"
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
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for edit_transcript_async.

    Args:
        lesson_id: ID of the lesson to edit
        words_per_group: Target number of words to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session

    Returns:
        True if edition was successful, False otherwise
    """
    return asyncio.run(
        edit_transcript_async(
            lesson_id=lesson_id,
            words_per_group=words_per_group,
            max_concurrency=max_concurrency,
            session=session,
        )
    )
