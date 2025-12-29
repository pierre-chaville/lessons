"""Lesson transcript correction using LLM"""
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
from models import Lesson, Segment, Metadata
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
    """Input segment with ID for correction"""
    id: int = Field(description="Segment index in the group")
    text: str = Field(description="Original text to be corrected")


class SegmentOutput(BaseModel):
    """Output segment with corrected text"""
    id: int = Field(description="Segment index matching the input")
    text: str = Field(description="Corrected text")


class TranscriptGroup(BaseModel):
    """Input: Group of segments to correct"""
    segments: List[SegmentInput] = Field(description="List of segments to correct")


class CorrectedTranscriptGroup(BaseModel):
    """Output: Group of corrected segments"""
    segments: List[SegmentOutput] = Field(description="List of corrected segments")


async def correct_segment_group_with_retry(
    group: List[tuple[int, Segment]],
    llm_with_structure,
    correction_prompt: str,
    max_retries: int = MAX_RETRIES
) -> List[tuple[int, str]]:
    """
    Correct a group of segments with retry logic for rate limits.
    
    Args:
        group: List of tuples (original_index, Segment or dict)
        llm_with_structure: LLM model with structured output
        correction_prompt: Prompt for correction
        max_retries: Maximum number of retry attempts
        
    Returns:
        List of tuples (original_index, corrected_text)
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await correct_segment_group(group, llm_with_structure, correction_prompt)
        
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
    llm_with_structure,
    correction_prompt: str
) -> List[tuple[int, str]]:
    """
    Correct a group of segments using the LLM with structured output.
    
    Args:
        group: List of tuples (original_index, Segment or dict)
        llm_with_structure: LLM model with structured output
        correction_prompt: Prompt for correction
        
    Returns:
        List of tuples (original_index, corrected_text)
    """
    try:
        # Prepare input data - handle both Segment objects and dicts
        # Use 1-based IDs to match the numbering shown to the LLM
        input_segments = []
        for i, (_, segment) in enumerate(group):
            if isinstance(segment, dict):
                text = segment['text']
            else:
                text = segment.text
            input_segments.append(SegmentInput(id=i+1, text=text))
        
        input_data = TranscriptGroup(segments=input_segments)
        
        # Create the prompt with the segments (numbered 1, 2, 3, ...)
        segments_text = "\n".join([
            f"{seg.id}. {seg.text}" 
            for seg in input_segments
        ])
        
        full_prompt = f"{correction_prompt}\n\nSegments to correct:\n{segments_text}"
        
        # Call LLM with structured output
        result = await llm_with_structure.ainvoke(full_prompt)
        
        # Map corrected segments back to original indices
        corrected = []
        for i, (original_idx, _) in enumerate(group):
            # Find the corrected segment by id (1-based)
            corrected_segment = next(
                (seg for seg in result.segments if seg.id == i+1),
                None
            )
            if corrected_segment:
                corrected.append((original_idx, corrected_segment.text))
            else:
                # Fallback to original text if not found
                logger.warning(f"Segment {i+1} not found in LLM response, using original")
                seg = group[i][1]
                original_text = seg['text'] if isinstance(seg, dict) else seg.text
                corrected.append((original_idx, original_text))
        
        return corrected
    
    except Exception as e:
        logger.error(f"Error correcting segment group: {e}", exc_info=True)
        # Return original texts on error
        result = []
        for original_idx, segment in group:
            text = segment['text'] if isinstance(segment, dict) else segment.text
            result.append((original_idx, text))
        return result


async def correct_transcript_async(
    lesson_id: int,
    segments_per_group: int = 10,
    max_concurrency: int = 10,
    session: Optional[Session] = None
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
        
        correction_prompt = correction_config.get(
            'prompt',
            'Please correct the following transcript, fixing any errors while maintaining the original meaning and style.'
        )
        
        # Get LLM model
        llm = get_llm_model(task_name='correction')
        
        # Add structured output
        llm_with_structure = llm.with_structured_output(CorrectedTranscriptGroup)
        
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
                    group, llm_with_structure, correction_prompt
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
        
        # Update lesson with corrected transcript (convert to dicts for JSON storage)
        lesson.corrected_transcript = [seg.model_dump() for seg in corrected_segments]
        
        # Save correction metadata
        metadata = Metadata(
            provider=config.get('provider'),
            model=correction_config.get('model'),
            temperature=correction_config.get('temperature'),
            prompt=correction_prompt
        )
        lesson.set_correction_metadata(metadata)
        
        # Commit changes
        session.add(lesson)
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
    session: Optional[Session] = None
) -> bool:
    """
    Synchronous wrapper for correct_transcript_async.
    
    Args:
        lesson_id: ID of the lesson to correct
        segments_per_group: Number of segments to process in each group
        max_concurrency: Maximum number of concurrent LLM calls
        session: Optional SQLModel session
        
    Returns:
        True if correction was successful, False otherwise
    """
    return asyncio.run(
        correct_transcript_async(
            lesson_id=lesson_id,
            segments_per_group=segments_per_group,
            max_concurrency=max_concurrency,
            session=session
        )
    )

