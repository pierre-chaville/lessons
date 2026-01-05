from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from pydantic import BaseModel
import shutil
from pathlib import Path

from database import create_db_and_tables, get_session
from models import Lesson, Course, Theme, Segment, Task, EditedPart, Source
import crud
import config as config_module
import search_utils

app = FastAPI(title="Lessons Manager API", version="1.0.0")

# Configure CORS for Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.on_event("startup")
# def on_startup():
#     """Initialize database on startup"""
#     create_db_and_tables()


@app.get("/")
def read_root():
    """Health check endpoint"""
    return {"status": "ok", "message": "Lessons Manager API"}


# ============== COURSE ENDPOINTS ==============


class CourseCreate(BaseModel):
    """Schema for creating a course"""

    name: str
    description: Optional[str] = None


class CourseUpdate(BaseModel):
    """Schema for updating a course"""

    name: Optional[str] = None
    description: Optional[str] = None


@app.get("/courses", response_model=List[Course], tags=["Courses"])
def get_courses(session: Session = Depends(get_session)):
    """Get all courses"""
    return crud.get_all_courses(session)


@app.get("/courses/{course_id}", response_model=Course, tags=["Courses"])
def get_course(course_id: int, session: Session = Depends(get_session)):
    """Get a specific course by ID"""
    course = crud.get_course(session, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@app.post("/courses", response_model=Course, status_code=201, tags=["Courses"])
def create_course(course_data: CourseCreate, session: Session = Depends(get_session)):
    """Create a new course"""
    return crud.create_course(
        session, name=course_data.name, description=course_data.description
    )


@app.patch("/courses/{course_id}", response_model=Course, tags=["Courses"])
def update_course(
    course_id: int, course_data: CourseUpdate, session: Session = Depends(get_session)
):
    """Update an existing course"""
    course = crud.update_course(
        session, course_id, name=course_data.name, description=course_data.description
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@app.delete("/courses/{course_id}", status_code=204, tags=["Courses"])
def delete_course(course_id: int, session: Session = Depends(get_session)):
    """Delete a course"""
    if not crud.delete_course(session, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    return None


# ============== THEME ENDPOINTS ==============


class ThemeCreate(BaseModel):
    """Schema for creating a theme"""

    name: str


class ThemeUpdate(BaseModel):
    """Schema for updating a theme"""

    name: str


@app.get("/themes", response_model=List[Theme], tags=["Themes"])
def get_themes(session: Session = Depends(get_session)):
    """Get all themes"""
    return crud.get_all_themes(session)


@app.get("/themes/{theme_id}", response_model=Theme, tags=["Themes"])
def get_theme(theme_id: int, session: Session = Depends(get_session)):
    """Get a specific theme by ID"""
    theme = crud.get_theme(session, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@app.post("/themes", response_model=Theme, status_code=201, tags=["Themes"])
def create_theme(theme_data: ThemeCreate, session: Session = Depends(get_session)):
    """Create a new theme"""
    return crud.create_theme(session, name=theme_data.name)


@app.patch("/themes/{theme_id}", response_model=Theme, tags=["Themes"])
def update_theme(
    theme_id: int, theme_data: ThemeUpdate, session: Session = Depends(get_session)
):
    """Update an existing theme"""
    theme = crud.update_theme(session, theme_id, name=theme_data.name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@app.delete("/themes/{theme_id}", status_code=204, tags=["Themes"])
def delete_theme(theme_id: int, session: Session = Depends(get_session)):
    """Delete a theme"""
    if not crud.delete_theme(session, theme_id):
        raise HTTPException(status_code=404, detail="Theme not found")
    return None


# ============== LESSON ENDPOINTS ==============


class LessonCreate(BaseModel):
    """Schema for creating a lesson"""

    title: str
    filename: str
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    duration: Optional[float] = None
    transcript: Optional[Dict[str, Any]] = None
    corrected_transcript: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    theme_ids: Optional[List[int]] = None


class LessonUpdate(BaseModel):
    """Schema for updating a lesson"""

    title: Optional[str] = None
    filename: Optional[str] = None
    course_id: Optional[int] = None
    date: Optional[datetime] = None
    duration: Optional[float] = None
    transcript: Optional[List[Segment]] = None
    corrected_transcript: Optional[List[Segment]] = None
    edited_transcript: Optional[List[EditedPart]] = None
    brief: Optional[str] = None
    summary: Optional[str] = None
    theme_ids: Optional[List[int]] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None


class LessonListResponse(BaseModel):
    """Lightweight lesson response for list view"""

    id: int
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    filename: str
    themes: List[Theme] = []
    course: Optional[Course] = None

    class Config:
        from_attributes = True


class LessonResponse(BaseModel):
    """Enhanced lesson response with theme details"""

    id: int
    title: str
    filename: str
    course_id: Optional[int]
    date: datetime
    duration: Optional[float]
    transcript: Optional[List[Segment]]
    corrected_transcript: Optional[List[Segment]]
    edited_transcript: Optional[List[EditedPart]]
    brief: Optional[str]
    summary: Optional[str]
    theme_ids: List[int]
    themes: List[Theme] = []
    course: Optional[Course] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None
    edited_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class SearchMatchSegment(BaseModel):
    start: float
    end: float
    text: str
    score: float
    exact: bool


class SearchLessonResult(BaseModel):
    id: int
    title: str
    date: datetime
    duration: Optional[float]
    brief: Optional[str]
    filename: str
    themes: List[Theme] = []
    course: Optional[Course] = None
    matches: List[SearchMatchSegment]
    match_count: int
    best_score: float

    class Config:
        from_attributes = True


@app.get("/lessons", response_model=List[LessonListResponse], tags=["Lessons"])
def get_lessons(
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    session: Session = Depends(get_session),
):
    """Get all lessons (lightweight response), optionally filtered by course"""
    lessons = crud.get_all_lessons(session, course_id=course_id)

    # Return lightweight response with only essential fields
    result = []
    for lesson in lessons:
        theme_ids = lesson.get_themes()
        themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []

        result.append(
            LessonListResponse(
                id=lesson.id,
                title=lesson.title,
                date=lesson.date,
                duration=lesson.duration,
                brief=lesson.brief,
                filename=lesson.filename,
                themes=themes,
                course=lesson.course,
            )
        )

    return result


@app.get("/lessons/{lesson_id}", response_model=LessonResponse, tags=["Lessons"])
def get_lesson(lesson_id: int, session: Session = Depends(get_session)):
    """Get a specific lesson by ID with full details"""
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []

    return LessonResponse(
        id=lesson.id,
        title=lesson.title,
        filename=lesson.filename,
        course_id=lesson.course_id,
        date=lesson.date,
        duration=lesson.duration,
        transcript=lesson.transcript,
        corrected_transcript=lesson.corrected_transcript,
        edited_transcript=lesson.edited_transcript,
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata,
        edited_metadata=lesson.edited_metadata,
    )


@app.post("/lessons", response_model=LessonResponse, status_code=201, tags=["Lessons"])
def create_lesson(lesson_data: LessonCreate, session: Session = Depends(get_session)):
    """Create a new lesson"""
    # Verify course exists if provided
    if lesson_data.course_id:
        course = crud.get_course(session, lesson_data.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

    # Verify themes exist if provided
    if lesson_data.theme_ids:
        themes = crud.get_themes_by_ids(session, lesson_data.theme_ids)
        if len(themes) != len(lesson_data.theme_ids):
            raise HTTPException(status_code=404, detail="One or more themes not found")

    lesson = crud.create_lesson(
        session,
        title=lesson_data.title,
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=lesson_data.transcript,
        corrected_transcript=lesson_data.corrected_transcript,
        summary=lesson_data.summary,
        theme_ids=lesson_data.theme_ids,
    )

    # Rename audio file to include lesson ID
    audio_dir = Path(__file__).parent / "data" / "audio"
    temp_file = audio_dir / lesson_data.filename
    if temp_file.exists():
        new_filename = (
            f"{lesson.id}_{lesson_data.filename.replace('temp_', '').split('_', 1)[-1]}"
        )
        new_path = audio_dir / new_filename
        temp_file.rename(new_path)

        # Update lesson with new filename
        lesson.filename = new_filename.split("_", 1)[-1]  # Store without the ID prefix
        session.add(lesson)
        session.commit()
        session.refresh(lesson)

    # Return with enriched data
    theme_ids = lesson.get_themes()
    themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []

    return LessonResponse(
        id=lesson.id,
        title=lesson.title,
        filename=lesson.filename,
        course_id=lesson.course_id,
        date=lesson.date,
        duration=lesson.duration,
        transcript=lesson.transcript,
        corrected_transcript=lesson.corrected_transcript,
        edited_transcript=lesson.edited_transcript,
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata,
        edited_metadata=lesson.edited_metadata,
    )


@app.patch("/lessons/{lesson_id}", response_model=LessonResponse, tags=["Lessons"])
def update_lesson(
    lesson_id: int, lesson_data: LessonUpdate, session: Session = Depends(get_session)
):
    """Update an existing lesson"""
    # Verify course exists if provided
    if lesson_data.course_id:
        course = crud.get_course(session, lesson_data.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

    # Verify themes exist if provided
    if lesson_data.theme_ids is not None:
        themes = crud.get_themes_by_ids(session, lesson_data.theme_ids)
        if len(themes) != len(lesson_data.theme_ids):
            raise HTTPException(status_code=404, detail="One or more themes not found")

    # Convert Segment objects to dicts for JSON storage
    transcript_data = None
    if lesson_data.transcript is not None:
        transcript_data = [
            seg.model_dump() if hasattr(seg, "model_dump") else seg
            for seg in lesson_data.transcript
        ]

    corrected_transcript_data = None
    if lesson_data.corrected_transcript is not None:
        corrected_transcript_data = [
            seg.model_dump() if hasattr(seg, "model_dump") else seg
            for seg in lesson_data.corrected_transcript
        ]

    # Convert EditedPart objects to dicts for JSON storage
    edited_transcript_data = None
    if lesson_data.edited_transcript is not None:
        edited_transcript_data = [
            part.model_dump() if hasattr(part, "model_dump") else part
            for part in lesson_data.edited_transcript
        ]

    lesson = crud.update_lesson(
        session,
        lesson_id,
        title=lesson_data.title,
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=transcript_data,
        corrected_transcript=corrected_transcript_data,
        edited_transcript=edited_transcript_data,
        brief=lesson_data.brief,
        summary=lesson_data.summary,
        theme_ids=lesson_data.theme_ids,
        transcript_metadata=lesson_data.transcript_metadata,
        correction_metadata=lesson_data.correction_metadata,
        summary_metadata=lesson_data.summary_metadata,
        edited_metadata=lesson_data.edited_metadata,
    )

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Return with enriched data
    theme_ids = lesson.get_themes()
    themes_list = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []

    return LessonResponse(
        id=lesson.id,
        title=lesson.title,
        filename=lesson.filename,
        course_id=lesson.course_id,
        date=lesson.date,
        duration=lesson.duration,
        transcript=lesson.transcript,
        corrected_transcript=lesson.corrected_transcript,
        edited_transcript=lesson.edited_transcript,
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes_list,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata,
        edited_metadata=lesson.edited_metadata,
    )


@app.delete("/lessons/{lesson_id}", status_code=204, tags=["Lessons"])
def delete_lesson(lesson_id: int, session: Session = Depends(get_session)):
    """Delete a lesson"""
    if not crud.delete_lesson(session, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    return None


@app.get("/lessons/{lesson_id}/pdf/summary", tags=["Lessons"])
def get_lesson_summary_pdf(lesson_id: int, session: Session = Depends(get_session)):
    """Generate and download PDF of the lesson summary"""
    from fastapi.responses import Response
    from pdf_reportlab import generate_lesson_summary_pdf

    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if not lesson.summary:
        raise HTTPException(status_code=404, detail="No summary available")

    # Extract prompt name from metadata if available
    prompt_name = None
    if lesson.summary_metadata:
        prompt_text = lesson.summary_metadata.get("prompt", "")
        # Check if prompt has format "[PromptName] ..."
        if prompt_text.startswith("["):
            end_bracket = prompt_text.find("]")
            if end_bracket > 0:
                prompt_name = prompt_text[1:end_bracket]

    # Generate PDF using ReportLab
    pdf_bytes = generate_lesson_summary_pdf(
        title=lesson.title,
        summary_markdown=lesson.summary,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
        prompt_name=prompt_name,
    )

    # Create safe filename
    safe_title = "".join(
        c for c in lesson.title if c.isalnum() or c in (" ", "-", "_")
    ).rstrip()
    filename = f"{safe_title}_summary.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/lessons/{lesson_id}/pdf/transcript", tags=["Lessons"])
def get_lesson_transcript_pdf(
    lesson_id: int,
    transcript_type: str = Query("corrected", regex="^(corrected|initial)$"),
    session: Session = Depends(get_session),
):
    """Generate and download PDF of the lesson transcript (without timestamps)"""
    from fastapi.responses import Response
    from pdf_reportlab import generate_lesson_transcript_pdf

    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Get the appropriate transcript
    transcript = (
        lesson.corrected_transcript
        if transcript_type == "corrected"
        else lesson.transcript
    )

    if not transcript or len(transcript) == 0:
        raise HTTPException(
            status_code=404, detail=f"No {transcript_type} transcript available"
        )

    # Generate PDF using ReportLab
    pdf_bytes = generate_lesson_transcript_pdf(
        title=lesson.title,
        transcript=transcript,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
        transcript_type=transcript_type,
    )

    # Create safe filename
    safe_title = "".join(
        c for c in lesson.title if c.isalnum() or c in (" ", "-", "_")
    ).rstrip()
    filename = f"{safe_title}_{transcript_type}_transcript.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/lessons/{lesson_id}/pdf/edited", tags=["Lessons"])
def get_lesson_edited_transcript_pdf(
    lesson_id: int, session: Session = Depends(get_session)
):
    """Generate and download PDF of the edited transcript with sources"""
    from fastapi.responses import Response
    from pdf_reportlab import generate_lesson_edited_transcript_pdf

    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if not lesson.edited_transcript or len(lesson.edited_transcript) == 0:
        raise HTTPException(status_code=404, detail="No edited transcript available")

    # Generate PDF using ReportLab
    pdf_bytes = generate_lesson_edited_transcript_pdf(
        title=lesson.title,
        edited_transcript=lesson.edited_transcript,
        date=lesson.date,
        course_name=lesson.course.name if lesson.course else None,
    )

    # Create safe filename
    safe_title = "".join(
        c for c in lesson.title if c.isalnum() or c in (" ", "-", "_")
    ).rstrip()
    filename = f"{safe_title}_edited.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/upload/audio", tags=["Lessons"])
async def upload_audio(
    file: UploadFile = File(...), session: Session = Depends(get_session)
):
    """Upload an audio file for a lesson"""
    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    # Create audio directory if it doesn't exist
    audio_dir = Path(__file__).parent / "data" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Save file with temporary name (will be renamed when lesson is created)
    temp_filename = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    temp_path = audio_dir / temp_filename

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    return {"filename": temp_filename, "original_filename": file.filename}


@app.get("/lessons/{lesson_id}/audio", tags=["Lessons"])
def get_lesson_audio(
    lesson_id: int, request: Request, session: Session = Depends(get_session)
):
    """Get audio file for a specific lesson with range request support"""
    from pathlib import Path
    from fastapi.responses import StreamingResponse
    import os

    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Construct audio file path: data/audio/{id}_{filename}
    audio_filename = f"{lesson_id}_{lesson.filename}"
    audio_path = Path(__file__).parent / "data" / "audio" / audio_filename

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    file_size = os.path.getsize(audio_path)
    range_header = request.headers.get("range")

    # Handle range request for seeking
    if range_header:
        # Parse range header (format: "bytes=start-end")
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0]) if byte_range[0] else 0
        end = (
            int(byte_range[1])
            if len(byte_range) > 1 and byte_range[1]
            else file_size - 1
        )

        # Validate range
        if start >= file_size or end >= file_size:
            raise HTTPException(status_code=416, detail="Range not satisfiable")

        chunk_size = end - start + 1

        def iter_file():
            with open(audio_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "audio/mpeg",
        }

        return StreamingResponse(
            iter_file(), status_code=206, headers=headers, media_type="audio/mpeg"
        )

    # Normal request without range
    def iter_file_full():
        with open(audio_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "audio/mpeg",
    }

    return StreamingResponse(iter_file_full(), headers=headers, media_type="audio/mpeg")


@app.get("/search", response_model=List[SearchLessonResult], tags=["Search"])
def search_corrected_transcript(
    q: Optional[str] = Query(None, description="Search string"),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    theme_id: Optional[int] = Query(None, description="Filter by theme ID"),
    threshold: int = Query(
        72, ge=0, le=100, description="Fuzzy match threshold (0-100)"
    ),
    max_matches_per_lesson: int = Query(
        20, ge=1, le=200, description="Max matched segments returned per lesson"
    ),
    session: Session = Depends(get_session),
):
    """Fuzzy search in corrected transcript segments.

    Returns results grouped by lesson, with the list of segments that matched.
    """
    if not q or not q.strip():
        return []

    lessons = crud.get_all_lessons(session, course_id=course_id)
    results: List[SearchLessonResult] = []

    for lesson in lessons:
        if theme_id is not None:
            lesson_theme_ids = lesson.get_themes()
            if theme_id not in lesson_theme_ids:
                continue

        matches = search_utils.find_matching_segments(
            lesson.corrected_transcript,
            q,
            threshold=float(threshold),
            max_matches=int(max_matches_per_lesson),
        )
        if not matches:
            continue

        theme_ids = lesson.get_themes()
        themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []

        best_score = float(matches[0]["score"]) if matches else 0.0

        results.append(
            SearchLessonResult(
                id=lesson.id,
                title=lesson.title,
                date=lesson.date,
                duration=lesson.duration,
                brief=lesson.brief,
                filename=lesson.filename,
                themes=themes,
                course=lesson.course,
                matches=matches,
                match_count=len(matches),
                best_score=best_score,
            )
        )

    results.sort(key=lambda r: (r.best_score, r.match_count, r.date), reverse=True)
    return results


# ============================================================
# Task Endpoints
# ============================================================


class TaskCreate(BaseModel):
    """Schema for creating a task"""

    task_type: str
    parameters: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """Schema for task response"""

    id: int
    task_type: str
    status: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    duration: Optional[float]
    parameters: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@app.post("/tasks", response_model=TaskResponse, tags=["Tasks"])
def create_task(task: TaskCreate, session: Session = Depends(get_session)):
    """Create and launch a new background task"""
    new_task = crud.create_task(
        session=session, task_type=task.task_type, parameters=task.parameters
    )
    return new_task


@app.get("/tasks", response_model=List[TaskResponse], tags=["Tasks"])
def get_tasks(session: Session = Depends(get_session)):
    """Get all tasks"""
    tasks = crud.get_all_tasks(session=session)
    return tasks


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
def get_task(task_id: int, session: Session = Depends(get_session)):
    """Get a specific task by ID"""
    task = crud.get_task(session=session, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/tasks/{task_id}", tags=["Tasks"])
def delete_task(task_id: int, session: Session = Depends(get_session)):
    """Delete a task"""
    success = crud.delete_task(session=session, task_id=task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@app.post("/tasks/test/{task_type}", response_model=TaskResponse, tags=["Tasks"])
def create_test_task(task_type: str, session: Session = Depends(get_session)):
    """Create a test task for development/testing purposes"""
    if task_type not in ["transcription", "correction", "summary"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid task type. Must be: transcription, correction, or summary",
        )

    new_task = crud.create_task(
        session=session,
        task_type=task_type,
        parameters={"test": True, "message": f"Test {task_type} task"},
    )
    return new_task


# ============================================================
# Configuration Endpoints
# ============================================================


class ConfigUpdate(BaseModel):
    """Schema for updating configuration"""

    config: Dict[str, Any]


@app.get("/config", tags=["Configuration"])
def get_configuration():
    """Get the current application configuration"""
    try:
        config = config_module.load_config()
        return config
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load configuration: {str(e)}"
        )


@app.put("/config", tags=["Configuration"])
def update_configuration(config_update: ConfigUpdate):
    """Update the application configuration"""
    try:
        updated_config = config_module.update_config(config_update.config)
        return {
            "message": "Configuration updated successfully",
            "config": updated_config,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}"
        )


@app.get("/config/{key_path}", tags=["Configuration"])
def get_configuration_value(key_path: str):
    """Get a specific configuration value using dot notation (e.g., 'whisper.model_size')"""
    try:
        value = config_module.get_config_value(key_path)
        if value is None:
            raise HTTPException(
                status_code=404, detail=f"Configuration key '{key_path}' not found"
            )
        return {"key": key_path, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get configuration value: {str(e)}"
        )


@app.post("/config/reset", tags=["Configuration"])
def reset_configuration():
    """Reset configuration to default values"""
    try:
        config_module.save_config(config_module.DEFAULT_CONFIG)
        return {
            "message": "Configuration reset to defaults",
            "config": config_module.DEFAULT_CONFIG,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reset configuration: {str(e)}"
        )
