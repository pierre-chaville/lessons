"""Upload router — /upload endpoints for audio files."""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from auth import require_roles
from storage import upload_audio_fileobj, s3_enabled

router = APIRouter(prefix="/upload", tags=["Lessons"])


@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Upload an audio file for a lesson to S3/R2."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    if not s3_enabled():
        raise HTTPException(status_code=500, detail="S3 is not configured")

    temp_filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    try:
        file.file.seek(0)
        upload_audio_fileobj(file.file, temp_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")
    finally:
        # Ensure temporary upload buffers/file handles are released promptly.
        await file.close()

    return {"filename": temp_filename, "original_filename": file.filename}
