"""Search service — fuzzy search and RAG search across lesson transcripts."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import bindparam, text
from sqlmodel import Session
from typing import List, Optional

import crud
import search_utils
from config import load_config
from models.course import Course
from schemas.search import SearchLessonResult, RagSearchCitation, RagSearchResponse
from schemas.course import CourseResponse
from schemas.theme import ThemeResponse
from hashid_utils import encode_id
from services.llm_utils import get_llm_model, register_token_usage_from_response
from services.rag_embeddings import (
    _embedding_literal,
    embed_texts_openrouter,
    rerank_texts_openrouter,
)


logger = logging.getLogger(__name__)


@dataclass
class RagCandidate:
    chunk_id: int
    lesson_id: int
    lesson_title: str
    lesson_date: datetime
    course_id: int | None
    variant: str
    chunk_index: int
    previous_paragraph: str
    content: str
    vector_score: float
    text_score: float
    combined_score: float


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


def _candidate_from_row(row) -> RagCandidate:
    return RagCandidate(
        chunk_id=int(row["chunk_id"]),
        lesson_id=int(row["lesson_id"]),
        lesson_title=str(row["lesson_title"] or ""),
        lesson_date=row["lesson_date"],
        course_id=int(row["course_id"]) if row["course_id"] is not None else None,
        variant=str(row["variant"] or ""),
        chunk_index=int(row["chunk_index"]),
        previous_paragraph=str(row["previous_paragraph"] or ""),
        content=str(row["content"] or ""),
        vector_score=float(row["vector_score"] or 0.0),
        text_score=float(row["text_score"] or 0.0),
        combined_score=float(row["combined_score"] or 0.0),
    )


def _fetch_vector_candidates(
    session: Session,
    query_embedding: list[float],
    lesson_ids: list[int] | None,
    variant: str,
    limit: int,
) -> list[RagCandidate]:
    where_parts = ["lc.variant = :variant"]
    if lesson_ids:
        where_parts.append("lc.lesson_id IN :lesson_ids")
    where_clause = "WHERE " + " AND ".join(where_parts)
    statement = text(f"""
        SELECT
            lc.id AS chunk_id,
            lc.lesson_id,
            l.title AS lesson_title,
            l.date AS lesson_date,
            l.course_id,
            lc.variant,
            lc.chunk_index,
            lc.previous_paragraph,
            lc.content,
            1 - (lc.embedding <=> CAST(:embedding AS vector)) AS vector_score,
            0.0 AS text_score,
            1 - (lc.embedding <=> CAST(:embedding AS vector)) AS combined_score
        FROM lesson_chunk lc
        JOIN lesson l ON l.id = lc.lesson_id
        {where_clause}
        ORDER BY lc.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)
    params = {
        "embedding": _embedding_literal(query_embedding),
        "variant": variant,
        "limit": max(1, int(limit)),
    }
    if lesson_ids:
        statement = statement.bindparams(bindparam("lesson_ids", expanding=True))
        params["lesson_ids"] = lesson_ids
    rows = session.execute(statement, params).mappings().all()
    return [_candidate_from_row(row) for row in rows]


def _fetch_full_text_candidates(
    session: Session,
    question: str,
    lesson_ids: list[int] | None,
    variant: str,
    limit: int,
) -> list[RagCandidate]:
    where_parts = [
        "lc.variant = :variant",
        "websearch_to_tsquery('simple', :question) @@ lc.content_tsv",
    ]
    if lesson_ids:
        where_parts.append("lc.lesson_id IN :lesson_ids")
    where_clause = "WHERE " + " AND ".join(where_parts)
    statement = text(f"""
        SELECT
            lc.id AS chunk_id,
            lc.lesson_id,
            l.title AS lesson_title,
            l.date AS lesson_date,
            l.course_id,
            lc.variant,
            lc.chunk_index,
            lc.previous_paragraph,
            lc.content,
            0.0 AS vector_score,
            ts_rank_cd(lc.content_tsv, websearch_to_tsquery('simple', :question)) AS text_score,
            ts_rank_cd(lc.content_tsv, websearch_to_tsquery('simple', :question)) AS combined_score
        FROM lesson_chunk lc
        JOIN lesson l ON l.id = lc.lesson_id
        {where_clause}
        ORDER BY text_score DESC
        LIMIT :limit
    """)
    params = {
        "question": question,
        "variant": variant,
        "limit": max(1, int(limit)),
    }
    if lesson_ids:
        statement = statement.bindparams(bindparam("lesson_ids", expanding=True))
        params["lesson_ids"] = lesson_ids
    rows = session.execute(statement, params).mappings().all()
    return [_candidate_from_row(row) for row in rows]


def _merge_candidates(candidates: list[RagCandidate]) -> list[RagCandidate]:
    by_id: dict[int, RagCandidate] = {}
    for candidate in candidates:
        existing = by_id.get(candidate.chunk_id)
        if not existing:
            by_id[candidate.chunk_id] = candidate
            continue
        existing.vector_score = max(existing.vector_score, candidate.vector_score)
        existing.text_score = max(existing.text_score, candidate.text_score)
        existing.combined_score = max(
            existing.combined_score,
            existing.vector_score + existing.text_score,
        )
    return sorted(by_id.values(), key=lambda item: item.combined_score, reverse=True)


def _context_for_candidate(candidate: RagCandidate, index: int) -> str:
    context_parts = []
    if candidate.previous_paragraph:
        context_parts.append(f"Previous paragraph:\n{candidate.previous_paragraph}")
    context_parts.append(f"Chunk:\n{candidate.content}")
    return (
        f"[{index}] Lesson: {candidate.lesson_title}\n"
        f"Variant: {candidate.variant}, chunk {candidate.chunk_index}\n"
        + "\n\n".join(context_parts)
    )


def _build_answer_prompt(
    question: str,
    candidates: list[RagCandidate],
    prompt_template: str,
) -> str:
    context = "\n\n---\n\n".join(
        _context_for_candidate(candidate, index)
        for index, candidate in enumerate(candidates, start=1)
    )
    template = (prompt_template or "").strip()
    if not template:
        template = (
            "Answer the user's question using only the provided lesson excerpts. "
            "Cite excerpts inline with their bracket numbers."
        )

    has_question_placeholder = "{question}" in template
    has_context_placeholder = "{context}" in template
    prompt = template.replace("{question}", question).replace("{context}", context)
    if not has_question_placeholder:
        prompt = f"{prompt}\n\nQuestion:\n{question}"
    if not has_context_placeholder:
        prompt = f"{prompt}\n\nLesson excerpts:\n{context}"
    return prompt


def _extract_used_reference_numbers(answer: str, max_reference_number: int) -> list[int]:
    seen: set[int] = set()
    refs: list[int] = []
    for match in re.finditer(r"\[(\d+)\]", answer or ""):
        reference_number = int(match.group(1))
        if reference_number < 1 or reference_number > max_reference_number:
            continue
        if reference_number in seen:
            continue
        seen.add(reference_number)
        refs.append(reference_number)
    return sorted(refs)


def _build_course_path(session: Session, course_id: int | None) -> str | None:
    if course_id is None:
        return None

    names: list[str] = []
    seen: set[int] = set()
    current_id: int | None = course_id
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        course = session.get(Course, current_id)
        if not course:
            break
        names.append(course.name)
        current_id = course.parent_id
    if not names:
        return None
    return " > ".join(reversed(names))


def _to_citation(
    session: Session,
    candidate: RagCandidate,
    score: float,
    reference_number: int,
) -> RagSearchCitation:
    snippet = candidate.content.strip()
    return RagSearchCitation(
        reference_number=reference_number,
        chunk_id=candidate.chunk_id,
        lesson_id=candidate.lesson_id,
        lesson_hashid=encode_id(candidate.lesson_id),
        lesson_title=candidate.lesson_title,
        lesson_course_path=_build_course_path(session, candidate.course_id),
        lesson_date=candidate.lesson_date,
        variant=candidate.variant,
        chunk_index=candidate.chunk_index,
        previous_paragraph=candidate.previous_paragraph,
        snippet=snippet,
        score=score,
    )


def answer_rag_question(
    question: str,
    session: Session,
    lesson_ids: Optional[list[int]] = None,
    variant: str = "edited",
) -> RagSearchResponse:
    clean_question = question.strip()
    if not clean_question:
        return RagSearchResponse(answer="", citations=[])

    scoped_lesson_ids = None
    if lesson_ids is not None:
        scoped_lesson_ids = [int(lesson_id) for lesson_id in lesson_ids if int(lesson_id) > 0]
        if not scoped_lesson_ids:
            return RagSearchResponse(
                answer="No lessons match the selected context scope.",
                citations=[],
            )

    config = load_config()
    rag_config = config.get("rag") if isinstance(config.get("rag"), dict) else {}
    source_variant = variant if variant in {"edited", "summary"} else "edited"
    embedding_model = str(rag_config.get("embedding_model") or "google/gemini-embedding-001")
    retrieval_k = max(1, int(rag_config.get("retrieval_k") or 40))
    full_text_search_k = max(1, int(rag_config.get("full_text_search_k") or 40))
    reranking_model = str(rag_config.get("reranking_model") or "cohere/rerank-4-pro")
    reranking_top_n = max(1, int(rag_config.get("reranking_top_n") or 8))
    llm_model = str(rag_config.get("llm_model") or "openai/gpt-5.4")
    llm_prompt = str(rag_config.get("llm_prompt") or "")

    query_embedding = embed_texts_openrouter([clean_question], embedding_model)[0]
    candidates = _merge_candidates([
        *_fetch_vector_candidates(session, query_embedding, scoped_lesson_ids, source_variant, retrieval_k),
        *_fetch_full_text_candidates(session, clean_question, scoped_lesson_ids, source_variant, full_text_search_k),
    ])

    if not candidates:
        return RagSearchResponse(
            answer="I could not find relevant lesson excerpts for this question in the selected scope.",
            citations=[],
        )

    selected = candidates[:reranking_top_n]
    rerank_scores_by_chunk_id: dict[int, float] = {}
    try:
        reranked = rerank_texts_openrouter(
            query=clean_question,
            documents=[candidate.content for candidate in candidates],
            model=reranking_model,
            top_n=reranking_top_n,
        )
        if reranked:
            selected = []
            for index, score in reranked:
                if 0 <= index < len(candidates):
                    candidate = candidates[index]
                    selected.append(candidate)
                    rerank_scores_by_chunk_id[candidate.chunk_id] = score
    except Exception as exc:
        logger.warning("RAG reranking failed; using combined retrieval scores: %s", exc)

    prompt = _build_answer_prompt(clean_question, selected, llm_prompt)
    llm = get_llm_model(
        provider="openrouter",
        model=llm_model,
        temperature=0.2,
    )
    response = llm.invoke(prompt)
    register_token_usage_from_response(response)
    answer = getattr(response, "content", str(response))

    used_reference_numbers = _extract_used_reference_numbers(str(answer or ""), len(selected))
    citations = []
    for reference_number in used_reference_numbers:
        candidate = selected[reference_number - 1]
        citations.append(
            _to_citation(
                session,
                candidate,
                rerank_scores_by_chunk_id.get(candidate.chunk_id, candidate.combined_score),
                reference_number,
            )
        )
    return RagSearchResponse(answer=str(answer or "").strip(), citations=citations)
