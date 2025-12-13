from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from pydantic import BaseModel
import shutil
from pathlib import Path

from database import create_db_and_tables, get_session
from models import Lesson, Course, Theme
import crud

app = FastAPI(title="Lessons Manager API", version="1.0.0")

# Configure CORS for Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize database on startup"""
    create_db_and_tables()


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
        session,
        name=course_data.name,
        description=course_data.description
    )


@app.patch("/courses/{course_id}", response_model=Course, tags=["Courses"])
def update_course(
    course_id: int,
    course_data: CourseUpdate,
    session: Session = Depends(get_session)
):
    """Update an existing course"""
    course = crud.update_course(
        session,
        course_id,
        name=course_data.name,
        description=course_data.description
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
    theme_id: int,
    theme_data: ThemeUpdate,
    session: Session = Depends(get_session)
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
    transcript: Optional[Dict[str, Any]] = None
    corrected_transcript: Optional[Dict[str, Any]] = None
    brief: Optional[str] = None
    summary: Optional[str] = None
    theme_ids: Optional[List[int]] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None


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
    transcript: Optional[Dict[str, Any]]
    corrected_transcript: Optional[Dict[str, Any]]
    brief: Optional[str]
    summary: Optional[str]
    theme_ids: List[int]
    themes: List[Theme] = []
    course: Optional[Course] = None
    transcript_metadata: Optional[Dict[str, Any]] = None
    correction_metadata: Optional[Dict[str, Any]] = None
    summary_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


@app.get("/lessons", response_model=List[LessonListResponse], tags=["Lessons"])
def get_lessons(
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    session: Session = Depends(get_session)
):
    """Get all lessons (lightweight response), optionally filtered by course"""
    lessons = crud.get_all_lessons(session, course_id=course_id)
    
    # Return lightweight response with only essential fields
    result = []
    for lesson in lessons:
        theme_ids = lesson.get_themes()
        themes = crud.get_themes_by_ids(session, theme_ids) if theme_ids else []
        
        result.append(LessonListResponse(
            id=lesson.id,
            title=lesson.title,
            date=lesson.date,
            duration=lesson.duration,
            brief=lesson.brief,
            filename=lesson.filename,
            themes=themes,
            course=lesson.course
        ))
    
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
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata
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
        theme_ids=lesson_data.theme_ids
    )
    
    # Rename audio file to include lesson ID
    audio_dir = Path(__file__).parent / "data" / "audio"
    temp_file = audio_dir / lesson_data.filename
    if temp_file.exists():
        new_filename = f"{lesson.id}_{lesson_data.filename.replace('temp_', '').split('_', 1)[-1]}"
        new_path = audio_dir / new_filename
        temp_file.rename(new_path)
        
        # Update lesson with new filename
        lesson.filename = new_filename.split('_', 1)[-1]  # Store without the ID prefix
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
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata
    )


@app.patch("/lessons/{lesson_id}", response_model=LessonResponse, tags=["Lessons"])
def update_lesson(
    lesson_id: int,
    lesson_data: LessonUpdate,
    session: Session = Depends(get_session)
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
    
    lesson = crud.update_lesson(
        session,
        lesson_id,
        title=lesson_data.title,
        filename=lesson_data.filename,
        course_id=lesson_data.course_id,
        date=lesson_data.date,
        duration=lesson_data.duration,
        transcript=lesson_data.transcript,
        corrected_transcript=lesson_data.corrected_transcript,
        brief=lesson_data.brief,
        summary=lesson_data.summary,
        theme_ids=lesson_data.theme_ids,
        transcript_metadata=lesson_data.transcript_metadata,
        correction_metadata=lesson_data.correction_metadata,
        summary_metadata=lesson_data.summary_metadata
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
        brief=lesson.brief,
        summary=lesson.summary,
        theme_ids=theme_ids,
        themes=themes_list,
        course=lesson.course,
        transcript_metadata=lesson.transcript_metadata,
        correction_metadata=lesson.correction_metadata,
        summary_metadata=lesson.summary_metadata
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
    from pathlib import Path
    from fastapi.responses import Response
    from weasyprint import HTML, CSS
    from io import BytesIO
    import markdown
    
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    if not lesson.summary:
        raise HTTPException(status_code=404, detail="No summary available")
    
    # Convert markdown to HTML
    md = markdown.Markdown(extensions=['extra', 'nl2br'])
    summary_html = md.convert(lesson.summary)
    
    # Create HTML document with proper styling
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{lesson.title} - Summary</title>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            h1 {{
                color: #4f46e5;
                border-bottom: 2px solid #4f46e5;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            h2 {{
                color: #6366f1;
                margin-top: 20px;
            }}
            h3 {{
                color: #818cf8;
            }}
            code {{
                background-color: #f3f4f6;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }}
            pre {{
                background-color: #f3f4f6;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            blockquote {{
                border-left: 4px solid #4f46e5;
                padding-left: 15px;
                margin-left: 0;
                font-style: italic;
                color: #666;
            }}
            ul, ol {{
                margin-left: 20px;
            }}
            .metadata {{
                font-size: 12px;
                color: #666;
                margin-bottom: 20px;
                padding: 10px;
                background-color: #f9fafb;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <h1>{lesson.title}</h1>
        <div class="metadata">
            <p><strong>Date:</strong> {lesson.date.strftime('%Y-%m-%d %H:%M') if lesson.date else 'N/A'}</p>
            {f'<p><strong>Course:</strong> {lesson.course.name}</p>' if lesson.course else ''}
        </div>
        <div class="content">
            {summary_html}
        </div>
    </body>
    </html>
    """
    
    # Generate PDF
    pdf_buffer = BytesIO()
    HTML(string=html_content).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    
    # Create safe filename
    safe_title = "".join(c for c in lesson.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filename = f"{safe_title}_summary.pdf"
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@app.get("/lessons/{lesson_id}/pdf/transcript", tags=["Lessons"])
def get_lesson_transcript_pdf(
    lesson_id: int, 
    transcript_type: str = Query("corrected", regex="^(corrected|initial)$"),
    session: Session = Depends(get_session)
):
    """Generate and download PDF of the lesson transcript (without timestamps)"""
    from pathlib import Path
    from fastapi.responses import Response
    from weasyprint import HTML
    from io import BytesIO
    
    lesson = crud.get_lesson(session, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    # Get the appropriate transcript
    transcript = lesson.corrected_transcript if transcript_type == "corrected" else lesson.transcript
    
    if not transcript or not transcript.get('segments'):
        raise HTTPException(status_code=404, detail=f"No {transcript_type} transcript available")
    
    # Extract text from segments (without timestamps)
    segments_text = "\n\n".join(segment['text'] for segment in transcript['segments'])
    
    # Create HTML document
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{lesson.title} - {transcript_type.capitalize()} Transcript</title>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.8;
                color: #333;
            }}
            h1 {{
                color: #4f46e5;
                border-bottom: 2px solid #4f46e5;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .metadata {{
                font-size: 12px;
                color: #666;
                margin-bottom: 20px;
                padding: 10px;
                background-color: #f9fafb;
                border-radius: 5px;
            }}
            .transcript {{
                text-align: justify;
                white-space: pre-wrap;
            }}
        </style>
    </head>
    <body>
        <h1>{lesson.title}</h1>
        <div class="metadata">
            <p><strong>Date:</strong> {lesson.date.strftime('%Y-%m-%d %H:%M') if lesson.date else 'N/A'}</p>
            {f'<p><strong>Course:</strong> {lesson.course.name}</p>' if lesson.course else ''}
            <p><strong>Transcript Type:</strong> {transcript_type.capitalize()}</p>
        </div>
        <div class="transcript">
            {segments_text}
        </div>
    </body>
    </html>
    """
    
    # Generate PDF
    pdf_buffer = BytesIO()
    HTML(string=html_content).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)
    
    # Create safe filename
    safe_title = "".join(c for c in lesson.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    filename = f"{safe_title}_{transcript_type}_transcript.pdf"
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@app.post("/upload/audio", tags=["Lessons"])
async def upload_audio(file: UploadFile = File(...), session: Session = Depends(get_session)):
    """Upload an audio file for a lesson"""
    # Validate file type
    if not file.content_type or not file.content_type.startswith('audio/'):
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
def get_lesson_audio(lesson_id: int, request: Request, session: Session = Depends(get_session)):
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
        end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
        
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
            iter_file(),
            status_code=206,
            headers=headers,
            media_type="audio/mpeg"
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
    
    return StreamingResponse(
        iter_file_full(),
        headers=headers,
        media_type="audio/mpeg"
    )
