"""Whisper transcription utilities"""
import time
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from sqlmodel import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config
from models import Lesson, Segment, TranscriptMetadata
from database import engine
import logging

logger = logging.getLogger(__name__)

# Global model cache
_model = None
_model_config = None

def get_whisper_model():
    """
    Get or initialize the Whisper model with lazy loading.
    Model is cached globally to avoid reloading.
    Import is delayed until first use for faster app startup.
    """
    global _model, _model_config
    
    # Load config from config.yaml
    config = load_config()
    
    # Get whisper config with defaults
    whisper_config = config.get("whisper", {})
    model_size = whisper_config.get("model_size", "large-v3")
    device = whisper_config.get("device", "cuda")
    compute_type = whisper_config.get("compute_type", "int8")
    
    current_config = (model_size, device, compute_type)
    
    # Check if model needs to be (re)loaded
    if _model is None or _model_config != current_config:
        # Import faster_whisper only when actually needed
        from faster_whisper import WhisperModel
        
        logger.info(f"Loading Whisper model {model_size} on {device} with compute type {compute_type}...")
        start_time = time.time()
        _model = WhisperModel(model_size_or_path=model_size, device=device, compute_type=compute_type)
        _model_config = current_config
        logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")
    
    return _model, model_size, device, compute_type

def transcribe_audio(
    audio_path: str, 
    language: Optional[str] = None,
    beam_size: int = 5,
    vad_filter: bool = True,
    initial_prompt: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Transcribe audio and return list of segments with timestamps and metadata.
    Model is loaded lazily on first call and cached for subsequent calls.
    
    Returns:
        Tuple of (segments, metadata_dict)
        - segments: List of dicts with keys: 'start', 'end', 'text'
        - metadata_dict: Dict with transcription parameters
    """
    # Get or initialize model
    model, model_size, device, compute_type = get_whisper_model()
    
    start_time = time.time()
    logger.info(f"Starting transcription of {audio_path}...")
    logger.info(f"Parameters: language={language}, beam_size={beam_size}, vad_filter={vad_filter}, initial_prompt={initial_prompt}")
    
    # Transcribe audio
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
    )

    seg_list = []
    for s in segments:
        seg_list.append({
            "start": s.start,
            "end": s.end,
            "text": s.text
        })
    
    duration = time.time() - start_time
    logger.info(f"Time taken to transcribe audio: {duration:.2f} seconds, i.e. {duration / 60:.2f} minutes.")
    logger.info(f"Transcribed {len(seg_list)} segments")
    
    # Prepare metadata
    metadata = {
        'model_size': model_size,
        'device': device,
        'compute_type': compute_type,
        'beam_size': beam_size,
        'vad_filter': vad_filter,
        'language': language,
        'initial_prompt': initial_prompt
    }
    
    return seg_list, metadata


def transcribe_lesson(
    lesson_id: int,
    session: Optional[Session] = None
) -> bool:
    """
    Transcribe a lesson's audio file and save the transcript to the database.
    
    Args:
        lesson_id: ID of the lesson to transcribe
        session: Optional SQLModel session (will create one if not provided)
        
    Returns:
        True if transcription was successful, False otherwise
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
        
        # Get audio file path
        audio_path = Path(__file__).parent.parent / "data" / "audio" / lesson.filename
        
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False
        
        logger.info(f"Transcribing lesson {lesson_id}: {lesson.title}")
        
        # Load config
        config = load_config()
        transcribe_config = config.get('transcribe', {})
        
        # Get transcription parameters
        language = transcribe_config.get('language', 'fr')
        beam_size = transcribe_config.get('beam_size', 5)
        vad_filter = transcribe_config.get('vad_filter', True)
        initial_prompt = transcribe_config.get('initial_prompt', '')
        
        # Transcribe audio
        segments_data, metadata = transcribe_audio(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt if initial_prompt else None
        )
        
        # Update lesson with transcript
        lesson.transcript = segments_data
        
        # Calculate and set duration from segments
        if segments_data:
            lesson.duration = segments_data[-1]['end']
        
        # Save transcript metadata
        transcript_metadata = TranscriptMetadata(
            model_size=metadata['model_size'],
            device=metadata['device'],
            compute_type=metadata['compute_type'],
            beam_size=metadata['beam_size'],
            vad_filter=metadata['vad_filter'],
            language=metadata['language'],
            initial_prompt=metadata['initial_prompt']
        )
        lesson.set_transcript_metadata(transcript_metadata)
        
        # Commit changes
        session.add(lesson)
        session.commit()
        
        logger.info(f"Successfully transcribed lesson {lesson_id}: {len(segments_data)} segments")
        return True
    
    except Exception as e:
        logger.error(f"Error transcribing lesson {lesson_id}: {e}", exc_info=True)
        if session:
            session.rollback()
        return False
    
    finally:
        if should_close_session and session:
            session.close()


