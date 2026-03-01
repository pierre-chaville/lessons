"""Tasks module — re-exports from services/ for backward compatibility."""

from services.llm_utils import get_llm_model
from services.correction import correct_transcript, correct_transcript_async
from services.edition import edit_transcript, edit_transcript_async
from services.extract_sources import extract_sources, extract_sources_async
from services.summary import generate_summary, generate_summary_async
from services.transcribe import transcribe_lesson, transcribe_audio
from services.sources import verify_lesson_sources, verify_lesson_sources_async

__all__ = [
    "get_llm_model",
    "correct_transcript",
    "correct_transcript_async",
    "edit_transcript",
    "edit_transcript_async",
    "extract_sources",
    "extract_sources_async",
    "generate_summary",
    "generate_summary_async",
    "transcribe_lesson",
    "transcribe_audio",
    "verify_lesson_sources",
    "verify_lesson_sources_async",
]
