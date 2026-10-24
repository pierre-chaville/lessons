"""Search router — /search endpoint for fuzzy transcript search."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from typing import List, Optional

from database import engine, get_session
from schemas.search import SearchLessonResult, RagSearchRequest
from services.search import iter_answer_rag_question, search_lessons

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=List[SearchLessonResult])
def search_corrected_transcript(
    q: Optional[str] = Query(None, description="Search string"),
    course_id: Optional[int] = Query(None, description="Filter by course ID"),
    theme_id: Optional[int] = Query(None, description="Filter by theme ID"),
    threshold: int = Query(72, ge=0, le=100, description="Fuzzy match threshold (0-100)"),
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

    return search_lessons(
        q=q,
        session=session,
        course_id=course_id,
        theme_id=theme_id,
        threshold=threshold,
        max_matches_per_lesson=max_matches_per_lesson,
    )


@router.post("/ai")
def ai_assistant_search(payload: RagSearchRequest):
    """Answer a natural language question using RAG over indexed lesson chunks.

    Streams NDJSON progress events (`search`, `rerank`, `generate`) followed by a result.
    """

    def event_stream():
        # Keep the DB session open for the full stream lifetime (Depends would close early).
        with Session(engine) as session:
            try:
                for event in iter_answer_rag_question(
                    question=payload.question,
                    lesson_ids=payload.lesson_ids,
                    variant=payload.variant,
                    session=session,
                ):
                    yield json.dumps(event) + "\n"
            except Exception as exc:
                logger.exception("RAG assistant search failed")
                yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
