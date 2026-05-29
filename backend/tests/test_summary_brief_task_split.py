"""Unit tests for split summary/brief generation tasks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.versioning import ContentType
from services import summary as summary_service


class _FakeSession:
    def __init__(self, lesson: SimpleNamespace):
        self._lesson = lesson
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = False

    def get(self, model, lesson_id: int):
        if getattr(model, "__name__", "") == "Lesson" and lesson_id == self._lesson.id:
            return self._lesson
        return None

    def add(self, _obj) -> None:
        return None

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_generate_summary_updates_summary_only(monkeypatch):
    lesson = SimpleNamespace(
        id=101,
        edited_transcript={"markdown": "Edited markdown"},
        summary="old summary",
        summary_metadata=None,
    )
    session = _FakeSession(lesson)
    update_calls: list[dict] = []

    monkeypatch.setattr(
        summary_service,
        "edited_transcript_markdown",
        lambda _edited: "Edited markdown",
    )
    monkeypatch.setattr(summary_service, "load_glossary_rules", lambda _session: [])
    monkeypatch.setattr(
        summary_service,
        "load_config",
        lambda: {
            "provider": "OpenAI",
            "summary": {
                "prompts": [{"name": "Default", "text": "Summarize this", "max_tokens": 1200}],
            },
            "alignment": {"summary_min_score": 0.2},
        },
    )
    monkeypatch.setattr(summary_service, "get_llm_model", lambda **_kwargs: object())

    async def _fake_generate_with_retry(*, input_text, llm, summary_prompt, input_label, max_retries=5):
        assert input_label == "Edited Text"
        assert "Edited markdown" in input_text
        return "Generated summary"

    monkeypatch.setattr(summary_service, "generate_summary_with_retry", _fake_generate_with_retry)
    monkeypatch.setattr(
        summary_service,
        "build_summary_alignment_metadata",
        lambda **_kwargs: {"summary_alignment": [], "summary_hash": "abc"},
    )

    def _fake_update_content(**kwargs):
        update_calls.append(kwargs)
        return None

    monkeypatch.setattr(summary_service, "update_content", _fake_update_content)

    success = await summary_service.generate_summary_async(
        lesson_id=lesson.id,
        prompt_type=None,
        session=session,
    )

    assert success is True
    assert lesson.summary_metadata is not None
    assert len(update_calls) == 1
    assert update_calls[0]["content_type"] == ContentType.SUMMARY
    assert update_calls[0]["new_content"] == "Generated summary"
    assert all(call["content_type"] != ContentType.BRIEF for call in update_calls)


@pytest.mark.anyio
async def test_generate_brief_updates_brief_only(monkeypatch):
    lesson = SimpleNamespace(
        id=202,
        edited_transcript=None,
        summary="A full lesson summary",
        summary_metadata=None,
    )
    session = _FakeSession(lesson)
    update_calls: list[dict] = []
    requested_task_names: list[str | None] = []

    monkeypatch.setattr(
        summary_service,
        "load_config",
        lambda: {
            "provider": "OpenAI",
            "brief": {"prompt": "Write a short brief", "max_tokens": 120},
        },
    )
    monkeypatch.setattr(summary_service, "load_glossary_rules", lambda _session: [])

    def _fake_get_llm_model(**kwargs):
        requested_task_names.append(kwargs.get("task_name"))
        return object()

    monkeypatch.setattr(summary_service, "get_llm_model", _fake_get_llm_model)

    async def _fake_generate_with_retry(*, input_text, llm, summary_prompt, input_label, max_retries=5):
        assert input_label == "Summary"
        assert "lesson summary" in input_text.lower()
        return "Generated brief"

    monkeypatch.setattr(summary_service, "generate_summary_with_retry", _fake_generate_with_retry)

    def _fake_update_content(**kwargs):
        update_calls.append(kwargs)
        return None

    monkeypatch.setattr(summary_service, "update_content", _fake_update_content)

    success = await summary_service.generate_brief_async(
        lesson_id=lesson.id,
        session=session,
    )

    assert success is True
    assert requested_task_names == ["brief"]
    assert len(update_calls) == 1
    assert update_calls[0]["content_type"] == ContentType.BRIEF
    assert update_calls[0]["new_content"] == "Generated brief"
    assert all(call["content_type"] != ContentType.SUMMARY for call in update_calls)
