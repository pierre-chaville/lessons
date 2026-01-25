"""Lesson transcript edition using LLM - rewrite in written style with sources"""

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


class SourceOutput(BaseModel):
    """A source citation used in the edited text"""

    type: str|None = Field(description="Type of source (e.g., Torah, Mishnah, Gemara, Midrash, etc.)")
    work: str|None = Field(description="Work title (e.g., Pirkei Avot)")
    ref: str|None = Field(description="Reference to the source (e.g., 4.2")
    standard_slug: str|None = Field(description="Standard slug in Sefaria for the source (e.g., Pirkei_Avot.4.2)")
    original_text: str|None = Field(description="Relevant quote or text from the source in the original language")
    translation_text: str|None = Field(description="Relevant quote or text from the source in the lesson (fr)")
    confidence: float|None = Field(description="Confidence score between 0 and 1 [1 = high confidence, 0 = low confidence, 0.5 = medium confidence]")


class EditedPartOutput(BaseModel):
    """Output: Edited part with segment numbers and sources"""

    start_segment: int = Field(
        description="Starting segment number (INCLUSIVE, 0-indexed within the group). "
        "This segment IS included in this edited part."
    )
    end_segment: int = Field(
        description="Ending segment number (INCLUSIVE, 0-indexed within the group). "
        "This segment IS included in this edited part. Must be >= start_segment."
    )
    text: str = Field(description="Rewritten text in clear, written style")
    sources: List[SourceOutput] = Field(
        default=[], description="List of sources cited in this section"
    )


class TranscriptGroupInput(BaseModel):
    """Input: Group of segments to edit"""

    segments: List[SegmentInput] = Field(description="List of transcript segments")


class EditedTranscriptGroupOutput(BaseModel):
    """Output: Group of edited parts with sources"""

    parts: List[EditedPartOutput] = Field(
        description="List of edited parts (can combine multiple segments into one part)"
    )


async def edit_segment_group_with_retry(
    group: List[Segment],
    llm_with_structure,
    edition_prompt: str,
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
            return await edit_segment_group(group, llm_with_structure, edition_prompt)

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


async def edit_segment_group(
    group: List[Segment], llm_with_structure, edition_prompt: str
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
            f"- Each segment can only appear in ONE edited part (no overlaps)\n"
            f"- Example: If you have segments 0-4, valid ranges are: [0,0], [1,2], [3,4] or [0,4] etc.\n"
        )

        full_prompt = (
            f"{edition_prompt}\n\n"
            f"Transcript to edit (use segment numbers for start_segment and end_segment):\n"
            f"{segments_text}"
            f"{segment_instructions}"
        )

        # Call LLM with structured output
        result = await llm_with_structure.ainvoke(full_prompt)

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
            text=combined_text,
            sources=[]
        )
        # Return tuple with timestamps
        return [(part, start_time, end_time)]


async def edit_transcript_async(
    lesson_id: int,
    segments_per_group: int = 100,
    max_concurrency: int = 10,
    session: Optional[Session] = None,
) -> bool:
    """
    Edit a lesson transcript by processing segments in parallel groups.

    Args:
        lesson_id: ID of the lesson to edit
        segments_per_group: Number of segments to process in each group
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
            "Each segment number can only appear in one edited part. Cite any sources mentioned.",
        )

        # Get LLM model
        llm = get_llm_model(task_name="edition")

        # Add structured output
        llm_with_structure = llm.with_structured_output(EditedTranscriptGroupOutput)

        # Split segments into groups
        segments = source_transcript
        segment_groups = []

        for i in range(0, len(segments), segments_per_group):
            group = segments[i : i + segments_per_group]
            segment_groups.append(group)

        logger.info(
            f"Editing lesson {lesson_id}: {len(segments)} segments "
            f"in {len(segment_groups)} groups with max concurrency {max_concurrency}"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)

        async def process_with_semaphore(group):
            async with semaphore:
                return await edit_segment_group_with_retry(
                    group, llm_with_structure, edition_prompt
                )

        # Process all groups in parallel (with concurrency limit)
        tasks = [process_with_semaphore(group) for group in segment_groups]
        results = await asyncio.gather(*tasks)

        # Flatten results - each result is a list of tuples: (EditedPartOutput, start_time, end_time)
        all_edited_parts = []
        for group_result in results:
            all_edited_parts.extend(group_result)

        # Convert to EditedPart model objects with Source objects
        edited_parts = []
        for part_tuple in all_edited_parts:
            # Unpack the tuple: (EditedPartOutput, start_time, end_time)
            part, start_time, end_time = part_tuple
            
            sources = [
                Source(
                    type=src.type,
                    work=src.work,
                    ref=src.ref,
                    standard_slug=src.standard_slug,
                    original_text=src.original_text,
                    translation_text=src.translation_text,
                    cited_excerpt=getattr(src, 'cited_excerpt', None),
                    confidence=src.confidence,
                )
                for src in part.sources
            ]

            edited_parts.append(
                EditedPart(
                    start=start_time, end=end_time, text=part.text, sources=sources
                )
            )

        # Update lesson with edited transcript (convert to dicts for JSON storage)
        lesson.edited_transcript = [part.model_dump() for part in edited_parts]

        # Save edition metadata
        metadata = Metadata(
            provider=config.get("provider"),
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
    segments_per_group: int = 100,
    max_concurrency: int = 10,
    session: Optional[Session] = None,
) -> bool:
    """
    Synchronous wrapper for edit_transcript_async.

    Args:
        lesson_id: ID of the lesson to edit
        segments_per_group: Number of segments to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session

    Returns:
        True if edition was successful, False otherwise
    """
    return asyncio.run(
        edit_transcript_async(
            lesson_id=lesson_id,
            segments_per_group=segments_per_group,
            max_concurrency=max_concurrency,
            session=session,
        )
    )
