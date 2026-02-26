"""Search service — fuzzy search across lesson transcripts."""

from sqlmodel import Session
from typing import List, Optional

import crud
import search_utils
from schemas.search import SearchLessonResult
from schemas.course import CourseResponse
from schemas.theme import ThemeResponse
from hashid_utils import encode_id


def _build_course_resp(course) -> CourseResponse | None:
    if course is None:
        return None
    return CourseResponse(
        id=course.id, hashid=encode_id(course.id),
        name=course.name, description=course.description,
    )


def _build_theme_resps(themes) -> list[ThemeResponse]:
    return [
        ThemeResponse(id=t.id, hashid=encode_id(t.id), name=t.name)
        for t in themes
    ]


def search_lessons(
    q: str,
    session: Session,
    course_id: Optional[int] = None,
    theme_id: Optional[int] = None,
    threshold: int = 72,
    max_matches_per_lesson: int = 20,
) -> List[SearchLessonResult]:
    """Fuzzy-search corrected transcript segments across all lessons.

    Returns results sorted by best_score desc, match_count desc, date desc.
    """
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
                hashid=encode_id(lesson.id),
                title=lesson.title,
                date=lesson.date,
                duration=lesson.duration,
                brief=lesson.brief,
                filename=lesson.filename,
                themes=_build_theme_resps(themes),
                course=_build_course_resp(lesson.course),
                matches=matches,
                match_count=len(matches),
                best_score=best_score,
            )
        )

    results.sort(key=lambda r: (r.best_score, r.match_count, r.date), reverse=True)
    return results
