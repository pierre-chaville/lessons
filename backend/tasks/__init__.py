"""Tasks module for handling asynchronous operations"""
from .llm_utils import get_llm_model
from .correction import correct_transcript, correct_transcript_async
from .summary import generate_summary, generate_summary_async
from .transcribe import transcribe_lesson, transcribe_audio

__all__ = [
    'get_llm_model',
    'correct_transcript',
    'correct_transcript_async',
    'generate_summary',
    'generate_summary_async',
    'transcribe_lesson',
    'transcribe_audio'
]
