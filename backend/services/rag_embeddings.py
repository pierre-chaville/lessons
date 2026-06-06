"""RAG chunking and embedding generation for lesson search."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx
from sqlalchemy import or_, text
from sqlmodel import Session, select

from config import load_config
from models.lesson import Lesson
from services.edited_transcript import edited_transcript_markdown, markdown_to_paragraphs
from services.llm_utils import _get_api_key_for_provider

logger = logging.getLogger(__name__)

RagVariant = Literal["edited", "summary"]
RAG_VARIANTS: tuple[RagVariant, ...] = ("summary", "edited")
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"
EMBEDDING_BATCH_SIZE = 32
RAG_HASH_RECOMPUTE_BATCH_SIZE = 100
OPENROUTER_EMBEDDING_MAX_ATTEMPTS = 5
OPENROUTER_EMBEDDING_INITIAL_RETRY_DELAY_SECONDS = 2.0
OPENROUTER_EMBEDDING_MAX_RETRY_DELAY_SECONDS = 60.0
OPENROUTER_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RagChunk:
    chunk_index: int
    previous_paragraph: str
    content: str


def compute_rag_hash(content: str, embedding_model: str) -> str | None:
    """Hash indexed content with the embedding model that produced the vector."""
    normalized_content = str(content or "").strip()
    normalized_model = str(embedding_model or "").strip()
    if not normalized_content or not normalized_model:
        return None
    payload = {
        "content": normalized_content,
        "embedding_model": normalized_model,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _lesson_variant_content(lesson: Lesson, variant: RagVariant) -> str:
    if variant == "summary":
        return str(lesson.summary or "").strip()
    return edited_transcript_markdown(lesson.edited_transcript).strip()


def _current_hash_attr(variant: RagVariant) -> str:
    return f"rag_{variant}_current_hash"


def _stored_hash_attr(variant: RagVariant) -> str:
    return f"rag_{variant}_stored_hash"


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    text_value = re.sub(r"\s+", " ", str(paragraph or "").strip())
    if not text_value or len(text_value) <= max_chars:
        return [text_value] if text_value else []

    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in text_value.split():
        word_len = len(word)
        separator_len = 1 if current else 0
        if current and current_len + separator_len + word_len > max_chars:
            parts.append(" ".join(current))
            current = [word]
            current_len = word_len
        else:
            current.append(word)
            current_len += separator_len + word_len
    if current:
        parts.append(" ".join(current))
    return parts


def build_rag_chunks(content: str, target_chars: int, max_chars: int) -> list[RagChunk]:
    """Build paragraph-preserving chunks with previous paragraph context stored separately."""
    target_chars = max(1, int(target_chars or 1))
    max_chars = max(target_chars, int(max_chars or target_chars))

    paragraphs: list[str] = []
    for paragraph in markdown_to_paragraphs(content):
        paragraphs.extend(_split_long_paragraph(paragraph, max_chars))

    chunks: list[RagChunk] = []
    current: list[str] = []
    current_start_index = 0

    def flush() -> None:
        nonlocal current, current_start_index
        if not current:
            return
        chunks.append(
            RagChunk(
                chunk_index=len(chunks),
                previous_paragraph=paragraphs[current_start_index - 1] if current_start_index > 0 else "",
                content="\n\n".join(current).strip(),
            )
        )
        current = []

    for paragraph_index, paragraph in enumerate(paragraphs):
        if not paragraph:
            continue
        candidate = "\n\n".join([*current, paragraph]).strip() if current else paragraph
        if current and (len(candidate) > max_chars or len("\n\n".join(current)) >= target_chars):
            flush()
        if not current:
            current_start_index = paragraph_index
        current.append(paragraph)

    flush()
    return chunks


def _embedding_literal(embedding: list[float]) -> str:
    values: list[str] = []
    for value in embedding:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Embedding contains a non-finite value")
        values.append(repr(number))
    return f"[{','.join(values)}]"


def _extract_embedding_from_item(item: Any) -> list[float] | None:
    if isinstance(item, dict):
        embedding = item.get("embedding")
    else:
        embedding = item
    if not isinstance(embedding, list):
        return None
    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError):
        return None


def _summarize_payload(payload: Any) -> str:
    try:
        serialized = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        serialized = str(payload)
    return serialized[:1000]


def _payload_error_status_code(error: Any) -> int | None:
    if not isinstance(error, dict):
        return None

    code = error.get("code")
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.isdigit():
        return int(code)

    status = str(error.get("status") or "")
    message = str(error.get("message") or "")
    if "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in message or "HTTP 429" in message:
        return 429
    return None


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None

    value = response.headers.get("Retry-After")
    if not value:
        return None

    try:
        delay = float(value)
        return max(0.0, delay)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
        delay = retry_at.timestamp() - time.time()
        return max(0.0, delay)
    except (TypeError, ValueError, OverflowError):
        return None


def _embedding_retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    retry_after = _retry_after_seconds(response)
    if retry_after is not None:
        return min(OPENROUTER_EMBEDDING_MAX_RETRY_DELAY_SECONDS, retry_after)

    base_delay = min(
        OPENROUTER_EMBEDDING_MAX_RETRY_DELAY_SECONDS,
        OPENROUTER_EMBEDDING_INITIAL_RETRY_DELAY_SECONDS * (2 ** attempt),
    )
    jitter = random.uniform(0, min(1.0, base_delay * 0.25))
    return base_delay + jitter


def _sleep_before_embedding_retry(
    attempt: int,
    reason: str,
    response: httpx.Response | None = None,
) -> None:
    delay = _embedding_retry_delay(attempt, response)
    logger.warning(
        "OpenRouter embeddings request failed with %s; retrying in %.1fs (attempt %s/%s)",
        reason,
        delay,
        attempt + 2,
        OPENROUTER_EMBEDDING_MAX_ATTEMPTS,
    )
    time.sleep(delay)


def embed_texts_openrouter(texts: list[str], model: str) -> list[list[float]]:
    """Call OpenRouter embeddings API for a batch of chunk texts."""
    if not texts:
        return []
    api_key = _get_api_key_for_provider("openrouter")
    if not api_key:
        raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY in .env")

    embeddings: list[list[float]] = []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + EMBEDDING_BATCH_SIZE]
            payload: Any = None
            for attempt in range(OPENROUTER_EMBEDDING_MAX_ATTEMPTS):
                response: httpx.Response | None = None
                try:
                    response = client.post(
                        OPENROUTER_EMBEDDINGS_URL,
                        headers=headers,
                        json={"model": model, "input": batch},
                    )
                    if response.status_code in OPENROUTER_RETRYABLE_STATUS_CODES:
                        if attempt < OPENROUTER_EMBEDDING_MAX_ATTEMPTS - 1:
                            _sleep_before_embedding_retry(attempt, f"HTTP {response.status_code}", response)
                            continue
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt < OPENROUTER_EMBEDDING_MAX_ATTEMPTS - 1:
                        _sleep_before_embedding_retry(attempt, exc.__class__.__name__)
                        continue
                    raise
                except httpx.HTTPStatusError as exc:
                    if (
                        exc.response.status_code in OPENROUTER_RETRYABLE_STATUS_CODES
                        and attempt < OPENROUTER_EMBEDDING_MAX_ATTEMPTS - 1
                    ):
                        _sleep_before_embedding_retry(attempt, f"HTTP {exc.response.status_code}", exc.response)
                        continue
                    raise

                error = payload.get("error") if isinstance(payload, dict) else None
                error_code = _payload_error_status_code(error)
                if error and error_code in OPENROUTER_RETRYABLE_STATUS_CODES:
                    if attempt < OPENROUTER_EMBEDDING_MAX_ATTEMPTS - 1:
                        _sleep_before_embedding_retry(attempt, f"payload error {error_code}")
                        continue
                if error:
                    raise ValueError(f"OpenRouter embeddings error: {_summarize_payload(error)}")
                break

            data = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(payload, dict) and data is None and "embedding" in payload:
                data = [payload]
            if isinstance(data, dict) and "embedding" in data:
                data = [data]
            if isinstance(payload, dict) and data is None:
                data = payload.get("embeddings")
            if not isinstance(data, list):
                raise ValueError(
                    "Unexpected OpenRouter embeddings response shape: "
                    f"{_summarize_payload(payload)}"
                )

            if data and all(isinstance(item, dict) and "index" in item for item in data):
                data = sorted(data, key=lambda item: int(item.get("index", 0)))

            batch_embeddings = []
            for item in data:
                embedding = _extract_embedding_from_item(item)
                if embedding is not None:
                    batch_embeddings.append(embedding)

            if len(batch_embeddings) != len(batch):
                raise ValueError(
                    "Unexpected OpenRouter embeddings count "
                    f"(expected {len(batch)}, got {len(batch_embeddings)}): "
                    f"{_summarize_payload(payload)}"
                )
            embeddings.extend(batch_embeddings)
    return embeddings


def rerank_texts_openrouter(
    query: str,
    documents: list[str],
    model: str,
    top_n: int,
) -> list[tuple[int, float]]:
    """Call OpenRouter rerank API and return (document_index, score)."""
    if not documents:
        return []
    api_key = _get_api_key_for_provider("openrouter")
    if not api_key:
        raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY in .env")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            OPENROUTER_RERANK_URL,
            headers=headers,
            json={
                "model": model,
                "query": query,
                "documents": documents,
                "top_n": max(1, int(top_n or 1)),
            },
        )
        response.raise_for_status()
        payload = response.json()

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("Unexpected OpenRouter rerank response shape")

    reranked: list[tuple[int, float]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("relevance_score", item.get("score", 0.0))
        try:
            reranked.append((int(index), float(score or 0.0)))
        except (TypeError, ValueError):
            continue
    return reranked


def recompute_current_rag_hashes(
    session: Session,
    embedding_model: str,
    batch_size: int = RAG_HASH_RECOMPUTE_BATCH_SIZE,
) -> int:
    """Refresh current RAG hash columns without materializing every lesson at once."""
    changed = 0
    last_id = 0
    batch_size = max(1, int(batch_size or RAG_HASH_RECOMPUTE_BATCH_SIZE))

    while True:
        statement = (
            select(Lesson)
            .where(Lesson.id > last_id)
            .order_by(Lesson.id)
            .limit(batch_size)
        )
        lessons = list(session.exec(statement).all())
        if not lessons:
            break

        lesson_ids = [int(lesson.id) for lesson in lessons if lesson.id is not None]
        if not lesson_ids:
            break

        batch_changed = 0
        for lesson in lessons:
            lesson_changed = False
            for variant in RAG_VARIANTS:
                content = _lesson_variant_content(lesson, variant)
                current_hash = compute_rag_hash(content, embedding_model)
                attr = _current_hash_attr(variant)
                if getattr(lesson, attr) != current_hash:
                    setattr(lesson, attr, current_hash)
                    changed += 1
                    batch_changed += 1
                    lesson_changed = True
            if lesson_changed:
                session.add(lesson)

        if batch_changed:
            session.commit()

        last_id = max(lesson_ids)
        session.expunge_all()

    return changed


def get_stale_rag_lessons(session: Session, limit: int | None = None) -> list[Lesson]:
    """Return lessons where a current RAG hash differs from the stored hash."""
    statement = select(Lesson).where(
        or_(
            Lesson.rag_summary_current_hash.is_distinct_from(Lesson.rag_summary_stored_hash),
            Lesson.rag_edited_current_hash.is_distinct_from(Lesson.rag_edited_stored_hash),
        )
    ).order_by(Lesson.id)
    if limit is not None:
        statement = statement.limit(max(1, int(limit)))
    return list(session.exec(statement).all())


def _replace_chunks(
    session: Session,
    lesson_id: int,
    variant: RagVariant,
    chunks: list[RagChunk],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("Chunk and embedding counts do not match")

    session.execute(
        text("DELETE FROM lesson_chunk WHERE lesson_id = :lesson_id AND variant = :variant"),
        {"lesson_id": lesson_id, "variant": variant},
    )
    for chunk, embedding in zip(chunks, embeddings):
        session.execute(
            text("""
                INSERT INTO lesson_chunk (
                    lesson_id, variant, chunk_index, previous_paragraph, content, embedding
                )
                VALUES (
                    :lesson_id, :variant, :chunk_index, :previous_paragraph, :content,
                    CAST(:embedding AS vector)
                )
            """),
            {
                "lesson_id": lesson_id,
                "variant": variant,
                "chunk_index": chunk.chunk_index,
                "previous_paragraph": chunk.previous_paragraph,
                "content": chunk.content,
                "embedding": _embedding_literal(embedding),
            },
        )


def rebuild_lesson_variant_chunks(
    session: Session,
    lesson: Lesson,
    variant: RagVariant,
    rag_config: dict[str, Any],
) -> int:
    """Rebuild chunks for one lesson variant if its current hash is stale."""
    current_hash = getattr(lesson, _current_hash_attr(variant))
    stored_hash = getattr(lesson, _stored_hash_attr(variant))
    if current_hash == stored_hash:
        return 0

    content = _lesson_variant_content(lesson, variant)
    if not current_hash or not content:
        session.execute(
            text("DELETE FROM lesson_chunk WHERE lesson_id = :lesson_id AND variant = :variant"),
            {"lesson_id": lesson.id, "variant": variant},
        )
        setattr(lesson, _stored_hash_attr(variant), current_hash)
        session.add(lesson)
        session.commit()
        return 0

    chunks = build_rag_chunks(
        content=content,
        target_chars=int(rag_config.get("chunk_target_chars", 1100)),
        max_chars=int(rag_config.get("chunk_max_chars", 1500)),
    )
    embeddings = embed_texts_openrouter(
        [chunk.content for chunk in chunks],
        model=str(rag_config.get("embedding_model") or "google/gemini-embedding-001"),
    )

    _replace_chunks(session, int(lesson.id), variant, chunks, embeddings)
    setattr(lesson, _stored_hash_attr(variant), current_hash)
    session.add(lesson)
    session.commit()
    return len(chunks)


def rebuild_stale_rag_embeddings(session: Session, limit: int | None = None) -> dict[str, int]:
    """Rebuild embeddings for all stale lesson variants."""
    config = load_config()
    rag_config = config.get("rag") if isinstance(config.get("rag"), dict) else {}
    embedding_model = str(rag_config.get("embedding_model") or "google/gemini-embedding-001")

    recompute_current_rag_hashes(session, embedding_model)
    stale_lessons = get_stale_rag_lessons(session, limit=limit)

    stats = {
        "stale_lessons": len(stale_lessons),
        "processed_variants": 0,
        "chunks_written": 0,
        "failed_variants": 0,
    }
    for lesson in stale_lessons:
        for variant in RAG_VARIANTS:
            if getattr(lesson, _current_hash_attr(variant)) == getattr(lesson, _stored_hash_attr(variant)):
                continue
            try:
                chunks_written = rebuild_lesson_variant_chunks(session, lesson, variant, rag_config)
                stats["processed_variants"] += 1
                stats["chunks_written"] += chunks_written
                session.refresh(lesson)
            except Exception:
                session.rollback()
                stats["failed_variants"] += 1
                logger.exception(
                    "Failed to rebuild RAG chunks for lesson_id=%s variant=%s",
                    lesson.id,
                    variant,
                )
        if lesson in session:
            session.expunge(lesson)
    return stats
