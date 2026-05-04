"""Deepgram batch transcription utilities"""
import gc
import time
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from sqlmodel import Session
from deepgram import DeepgramClient

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config
from models import Lesson
from schemas import TranscriptMetadata
from database import engine
from memory_usage import format_memory_mb, get_rss_memory_mb
from storage import download_audio_bytes, get_audio_object_key, s3_enabled
import logging

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Get the Deepgram API key from environment."""
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY environment variable is not set")
    return api_key


def transcribe_audio(
    audio_bytes: bytes,
    language: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Transcribe audio using Deepgram's batch (pre-recorded) API.

    Returns:
        Tuple of (segments, metadata_dict)
        - segments: List of dicts with keys: 'start', 'end', 'text'
        - metadata_dict: Dict with transcription parameters
    """

    api_key = _get_api_key()
    client = DeepgramClient(api_key=api_key)

    try:
        start_time = time.time()
        logger.info("Starting Deepgram transcription...")
        logger.info(f"Parameters: language={language}")
        response = client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="whisper-large",
            smart_format=True,
            utterances=True,
            # language='multi' # language or "fr",
            language=language or "fr",
            request_options={
                "timeout_in_seconds": 600,
                "max_retries": 3,
            },
        )
        result = response.results

        # Extract segments from utterances
        seg_list = []
        if result.utterances:
            for utterance in result.utterances:
                seg_list.append(
                    {
                        "start": utterance.start,
                        "end": utterance.end,
                        "text": utterance.transcript,
                    }
                )
        elif result.channels:
            # Fallback: build segments from paragraphs/sentences in the first channel
            for alt in result.channels[0].alternatives:
                if alt.paragraphs and alt.paragraphs.paragraphs:
                    for para in alt.paragraphs.paragraphs:
                        for sentence in para.sentences:
                            seg_list.append(
                                {
                                    "start": sentence.start,
                                    "end": sentence.end,
                                    "text": sentence.text,
                                }
                            )

        duration = time.time() - start_time
        logger.info(
            "Time taken to transcribe audio: %.2f seconds, i.e. %.2f minutes.",
            duration,
            duration / 60,
        )
        logger.info(f"Transcribed {len(seg_list)} segments")

        metadata = {
            "model": "nova-3",
            "language": language or "fr",
            "provider": "deepgram",
        }

        return seg_list, metadata
    finally:
        # Explicitly close client resources between jobs to avoid connection buildup.
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            close_fn()


def transcribe_lesson(
    lesson_id: int,
    session: Optional[Session] = None,
) -> bool:
    """
    Transcribe a lesson's audio file using Deepgram and save the transcript to the database.

    Args:
        lesson_id: ID of the lesson to transcribe
        session: Optional SQLModel session (will create one if not provided)

    Returns:
        True if transcription was successful, False otherwise
    """
    should_close_session = False
    audio_bytes = None

    try:
        if session is None:
            session = Session(engine)
            should_close_session = True

        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return False

        if not s3_enabled():
            logger.error("S3 is not configured")
            return False

        audio_key = get_audio_object_key(lesson_id, lesson.filename)
        try:
            mem_before_download = get_rss_memory_mb()
            logger.info(
                "Memory before audio download for lesson %s: %s",
                lesson_id,
                format_memory_mb(mem_before_download),
            )
            audio_bytes = download_audio_bytes(audio_key)
            mem_after_download = get_rss_memory_mb()
            logger.info(
                "Memory after audio download for lesson %s: %s (audio_size=%.2f MB)",
                lesson_id,
                format_memory_mb(mem_after_download),
                len(audio_bytes) / (1024.0 * 1024.0),
            )
        except Exception as e:
            logger.error(f"Audio file not found in S3: {audio_key} ({e})")
            return False

        logger.info(f"Transcribing lesson {lesson_id}: {lesson.title}")

        config = load_config()
        transcribe_config = config.get("transcribe", {})
        language = transcribe_config.get("language", "fr")

        mem_before_transcription = get_rss_memory_mb()
        logger.info(
            "Memory before Deepgram call for lesson %s: %s",
            lesson_id,
            format_memory_mb(mem_before_transcription),
        )
        segments_data, metadata = transcribe_audio(audio_bytes, language=language)
        mem_after_transcription = get_rss_memory_mb()
        logger.info(
            "Memory after Deepgram call for lesson %s: %s",
            lesson_id,
            format_memory_mb(mem_after_transcription),
        )

        # Update lesson with transcript and corrected_transcript
        lesson.transcript = segments_data
        lesson.corrected_transcript = segments_data

        # Calculate and set duration from segments
        if segments_data:
            lesson.duration = segments_data[-1]["end"]

        # Save transcript metadata
        transcript_metadata = TranscriptMetadata(
            provider=metadata["provider"],
            model=metadata["model"],
            language=metadata["language"],
        )
        lesson.set_transcript_metadata(transcript_metadata)

        session.add(lesson)
        session.commit()
        mem_after_commit = get_rss_memory_mb()
        logger.info(
            "Memory after transcription commit for lesson %s: %s",
            lesson_id,
            format_memory_mb(mem_after_commit),
        )

        logger.info(f"Successfully transcribed lesson {lesson_id}: {len(segments_data)} segments")
        return True

    except Exception as e:
        logger.error(f"Error transcribing lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False

    finally:
        # Proactively release large temporary objects from this job.
        audio_bytes = None
        gc.collect()
        logger.info(
            "Memory after transcription cleanup for lesson %s: %s",
            lesson_id,
            format_memory_mb(get_rss_memory_mb()),
        )
        if should_close_session and session:
            session.close()
