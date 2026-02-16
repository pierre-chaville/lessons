"""Whisper transcription utilities"""
import time
import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from sqlmodel import Session

# Add CUDA to PATH for Windows (needed for cuDNN DLLs)
# TODO: to modify to use api instead of local whisper
if sys.platform != "win32":
    print(f"Current PATH: {os.environ.get('PATH', 'NOT SET')[:200]}...")
    
    # Common CUDA and cuDNN installation paths (check both \bin and \bin\x64)
    cuda_paths = [
        # Standalone cuDNN installations (from .exe installer) - versioned structure
        # Format: C:\Program Files\NVIDIA\CUDNN\v9.x\bin\{cuda_version}\x64
        # Prioritize 12.x versions as they're more stable/compatible
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.18\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.4\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.4\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.4\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.4\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.3\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.3\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.3\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.3\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.2\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.2\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.2\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.2\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin\12.6\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.0\bin\13.1\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.0\bin\13.0\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.0\bin\12.9\x64",
        r"C:\Program Files\NVIDIA\CUDNN\v9.0\bin\12.6\x64",
        # Older cuDNN structure (non-versioned)
        r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.4\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.3\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.2\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.1\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.0\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.5\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.4\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.3\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.2\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.1\bin",
        r"C:\Program Files\NVIDIA Corporation\CUDNN\v9.0\bin",
        # CUDA Toolkit paths with cuDNN
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.5\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.5\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.3\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.3\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.2\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin\x64",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin",
        r"C:\Program Files\NVIDIA\CUDA\v13.0\bin\x64",
        r"C:\Program Files\NVIDIA\CUDA\v13.0\bin",
        r"C:\Program Files\NVIDIA\CUDA\v12.6\bin\x64",
        r"C:\Program Files\NVIDIA\CUDA\v12.6\bin",
        r"C:\Program Files\NVIDIA\CUDA\v12.5\bin\x64",
        r"C:\Program Files\NVIDIA\CUDA\v12.5\bin",
        r"C:\Program Files\NVIDIA\CUDA\v11.8\bin\x64",
        r"C:\Program Files\NVIDIA\CUDA\v11.8\bin",
    ]
    
    # Check which paths exist
    print("Checking CUDA paths:")
    for cuda_path in cuda_paths:
        exists = Path(cuda_path).exists()
        in_path = cuda_path in os.environ.get("PATH", "")
        print(f"  {cuda_path}: exists={exists}, in_PATH={in_path}")
        if exists:
            # Check if cudnn_ops64_9.dll is in this directory
            dll_path = Path(cuda_path) / "cudnn_ops64_9.dll"
            print(f"    cudnn_ops64_9.dll exists: {dll_path.exists()}")
    
    # Search for cuDNN DLL in known paths and add to PATH if found
    cudnn_found = False
    cudnn_cuda_version = None
    for cuda_path in cuda_paths:
        if Path(cuda_path).exists():
            dll_path = Path(cuda_path) / "cudnn_ops64_9.dll"
            if dll_path.exists():
                print(f"✓ Found cudnn_ops64_9.dll in: {cuda_path}")
                # Extract CUDA version from path (e.g., "12.9" from "...bin\12.9\x64")
                path_parts = cuda_path.split(os.sep)
                for i, part in enumerate(path_parts):
                    if part == "bin" and i + 1 < len(path_parts):
                        potential_version = path_parts[i + 1]
                        if potential_version.replace(".", "").isdigit():
                            cudnn_cuda_version = potential_version
                            break
                
                if cuda_path not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = cuda_path + os.pathsep + os.environ.get("PATH", "")
                    print(f"✓ Added cuDNN path to environment: {cuda_path}")
                    if cudnn_cuda_version:
                        print(f"  (cuDNN built for CUDA {cudnn_cuda_version})")
                else:
                    print(f"✓ cuDNN path already in PATH: {cuda_path}")
                    if cudnn_cuda_version:
                        print(f"  (cuDNN built for CUDA {cudnn_cuda_version})")
                cudnn_found = True
                break
    
    # Also ensure CUDA Toolkit bin directory is in PATH for cuBLAS, etc.
    if cudnn_found and cudnn_cuda_version:
        # Try to find matching CUDA toolkit
        cuda_major = cudnn_cuda_version.split('.')[0]
        potential_cuda_paths = [
            rf"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v{cudnn_cuda_version}\bin",
            rf"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v{cuda_major}.0\bin",
            rf"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v{cudnn_cuda_version}\bin\x64",
            rf"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v{cuda_major}.0\bin\x64",
        ]
        
        for cuda_bin in potential_cuda_paths:
            if Path(cuda_bin).exists():
                cublas_dll = Path(cuda_bin) / f"cublasLt64_{cuda_major}.dll"
                if cublas_dll.exists():
                    if cuda_bin not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = cuda_bin + os.pathsep + os.environ.get("PATH", "")
                        print(f"✓ Added CUDA Toolkit path: {cuda_bin}")
                    else:
                        print(f"✓ CUDA Toolkit path already in PATH: {cuda_bin}")
                    break
        else:
            print(f"⚠ WARNING: Could not find CUDA {cudnn_cuda_version} Toolkit installation")
            print(f"  cuDNN {cudnn_cuda_version} requires CUDA {cudnn_cuda_version} libraries")
            print(f"  The worker will attempt to use CPU instead.")
    
    if not cudnn_found:
        print("⚠ WARNING: cudnn_ops64_9.dll not found in standard paths!")
        print("  Searching all PATH directories for cudnn_ops64_9.dll...")
        
        # Search all PATH directories for the DLL
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for path_dir in path_dirs:
            if path_dir and Path(path_dir).exists():
                dll_path = Path(path_dir) / "cudnn_ops64_9.dll"
                if dll_path.exists():
                    print(f"  ✓ Found cudnn_ops64_9.dll in: {path_dir}")
                    cudnn_found = True
                    break
        
        if not cudnn_found:
            print("  ✗ cudnn_ops64_9.dll not found in any PATH directory!")
            print("  ")
            print("  To fix this, you need to find where cuDNN was installed and add it to PATH.")
            print("  Common locations to check:")
            print("    - C:\\Program Files\\NVIDIA\\CUDNN\\")
            print("    - C:\\Program Files\\NVIDIA Corporation\\CUDNN\\")
            print("    - Your user AppData folder")
            print("  ")
            print("  Or manually add the cuDNN bin directory to your system PATH.")
            print("  The worker will attempt to use CPU instead of CUDA.")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import load_config
from models import Lesson
from schemas import Segment, TranscriptMetadata
from database import engine
import logging

logger = logging.getLogger(__name__)

# Global model cache
_model = None
_model_config = None

def get_whisper_model(force_device=None):
    """
    Get or initialize the Whisper model with lazy loading.
    Model is cached globally to avoid reloading.
    Import is delayed until first use for faster app startup.
    
    Args:
        force_device: If provided, overrides the device from config (e.g., 'cpu', 'cuda')
    """
    global _model, _model_config
    
    # Load config from database (seeded from config.yaml)
    config = load_config()
    
    # Get whisper config with defaults
    whisper_config = config.get("whisper", {})
    model_size = whisper_config.get("model_size", "large-v3")
    device = force_device if force_device is not None else whisper_config.get("device", "cuda")
    compute_type = whisper_config.get("compute_type", "int8")
    
    current_config = (model_size, device, compute_type)
    
    # Check if model needs to be (re)loaded
    if _model is None or _model_config != current_config:
        # Import faster_whisper only when actually needed
        from faster_whisper import WhisperModel
        
        logger.info(f"Loading Whisper model {model_size} on {device} with compute type {compute_type}...")
        start_time = time.time()
        
        try:
            _model = WhisperModel(model_size_or_path=model_size, device=device, compute_type=compute_type)
            _model_config = current_config
            logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")
        except Exception as e:
            # If CUDA fails, fall back to CPU
            if device == "cuda":
                logger.warning(f"Failed to load model on CUDA: {e}")
                logger.info("Falling back to CPU...")
                device = "cpu"
                compute_type = "int8"
                current_config = (model_size, device, compute_type)
                
                _model = WhisperModel(model_size_or_path=model_size, device=device, compute_type=compute_type)
                _model_config = current_config
                logger.info(f"Model loaded on CPU in {time.time() - start_time:.2f} seconds")
            else:
                raise
    
    # Return model and its config (use cached config if model wasn't reloaded)
    return _model, _model_config[0], _model_config[1], _model_config[2]

def transcribe_audio(
    audio_path: str, 
    language: Optional[str] = None,
    beam_size: int = 5,
    vad_filter: bool = True,
    initial_prompt: Optional[str] = None,
    force_device: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Transcribe audio and return list of segments with timestamps and metadata.
    Model is loaded lazily on first call and cached for subsequent calls.
    
    Args:
        force_device: Force a specific device ('cpu' or 'cuda'), overrides config
    
    Returns:
        Tuple of (segments, metadata_dict)
        - segments: List of dicts with keys: 'start', 'end', 'text'
        - metadata_dict: Dict with transcription parameters
    """
    # Get or initialize model (with optional device override)
    model, model_size, device, compute_type = get_whisper_model(force_device=force_device)
    
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
        audio_dir = Path(__file__).parent.parent / "data" / "audio"
        audio_path = audio_dir / (str(lesson_id) + "_" + lesson.filename)
        
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
        
        # Transcribe audio (with fallback to CPU if cuDNN fails)
        try:
            segments_data, metadata = transcribe_audio(
                str(audio_path),
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                initial_prompt=initial_prompt if initial_prompt else None
            )
        except RuntimeError as e:
            if "cuDNN" in str(e) or "CUDA" in str(e):
                logger.warning(f"CUDA/cuDNN error during transcription: {e}. Retrying with CPU...")
                # Clear cached model to force reload
                global _model, _model_config
                _model = None
                _model_config = None
                
                # Retry transcription with CPU (force_device='cpu' overrides config)
                segments_data, metadata = transcribe_audio(
                    str(audio_path),
                    language=language,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                    initial_prompt=initial_prompt if initial_prompt else None,
                    force_device='cpu'
                )
                logger.info("Successfully transcribed on CPU after CUDA failure")
            else:
                raise
        
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


