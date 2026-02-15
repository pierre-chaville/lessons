"""Upload router — /upload endpoints for audio files."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session

from database import get_session
from storage import upload_audio_fileobj, s3_enabled

router = APIRouter(prefix="/upload", tags=["Lessons"])


@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...), session: Session = Depends(get_session)
):
    """Upload an audio file for a lesson to S3/R2."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    if not s3_enabled():
        raise HTTPException(status_code=500, detail="S3 is not configured")

    temp_filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    try:
        upload_audio_fileobj(file.file, temp_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    return {"filename": temp_filename, "original_filename": file.filename}
