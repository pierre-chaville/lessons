"""Worker task dispatch tests for summary/brief split."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def _import_worker_with_stubs(monkeypatch):
    # Ensure backend root is importable as top-level modules.
    backend_root = str(Path(__file__).resolve().parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    fake_database = types.ModuleType("database")
    fake_database.engine = object()
    monkeypatch.setitem(sys.modules, "database", fake_database)

    fake_models = types.ModuleType("models")
    fake_models.ModelPreset = type("ModelPreset", (), {})
    fake_models.Task = type("Task", (), {})
    monkeypatch.setitem(sys.modules, "models", fake_models)

    fake_models_lesson = types.ModuleType("models.lesson")
    fake_models_lesson.Lesson = type("Lesson", (), {})
    monkeypatch.setitem(sys.modules, "models.lesson", fake_models_lesson)

    fake_services = types.ModuleType("services")
    fake_services.__path__ = []
    for name in (
        "correct_transcript",
        "edit_transcript",
        "extract_sources",
        "generate_brief",
        "generate_summary",
        "transcribe_lesson",
        "verify_lesson_sources",
    ):
        setattr(fake_services, name, lambda **_kwargs: True)
    monkeypatch.setitem(sys.modules, "services", fake_services)

    fake_lessons_service = types.ModuleType("services.lessons")
    fake_lessons_service.set_lesson_step_status = lambda **_kwargs: None
    fake_services.lessons = fake_lessons_service
    monkeypatch.setitem(sys.modules, "services.lessons", fake_lessons_service)

    fake_llm_utils = types.ModuleType("services.llm_utils")
    fake_llm_utils.get_token_usage_tracker = lambda: {}
    fake_llm_utils.reset_token_usage_tracker = lambda: None
    monkeypatch.setitem(sys.modules, "services.llm_utils", fake_llm_utils)

    fake_rag_embeddings = types.ModuleType("services.rag_embeddings")
    fake_rag_embeddings.rebuild_stale_rag_embeddings = lambda _session, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "services.rag_embeddings", fake_rag_embeddings)

    fake_memory_usage = types.ModuleType("memory_usage")
    fake_memory_usage.format_memory_mb = lambda _value: "0 MB"
    fake_memory_usage.get_rss_memory_mb = lambda: 0.0
    monkeypatch.setitem(sys.modules, "memory_usage", fake_memory_usage)

    sys.modules.pop("worker", None)
    return importlib.import_module("worker")


def test_task_uses_flex_only_when_requested(monkeypatch):
    worker = _import_worker_with_stubs(monkeypatch)

    assert worker.task_uses_flex(SimpleNamespace(parameters={"use_flex": True})) is True
    assert worker.task_uses_flex(SimpleNamespace(parameters={"use_flex": False})) is False
    assert worker.task_uses_flex(SimpleNamespace(parameters={"lesson_id": 1})) is False
    assert worker.task_uses_flex(SimpleNamespace(parameters=None)) is False


def test_task_worker_loop_polls_requested_flex_queue(monkeypatch):
    worker = _import_worker_with_stubs(monkeypatch)
    task = SimpleNamespace(id=10, task_type="summary", parameters={"use_flex": True})
    calls = {"filters": [], "processed": []}

    class FakeSession:
        def __init__(self, _engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_get_pending_task(_session, use_flex=None):
        calls["filters"].append(use_flex)
        return task

    def fake_process_task(_session, queued_task):
        calls["processed"].append(queued_task.id)
        worker.should_stop = True

    monkeypatch.setattr(worker, "Session", FakeSession)
    monkeypatch.setattr(worker, "get_pending_task", fake_get_pending_task)
    monkeypatch.setattr(worker, "process_task", fake_process_task)

    worker.should_stop = False
    try:
        worker.task_worker_loop("flex-test", True)
    finally:
        worker.should_stop = True

    assert calls == {"filters": [True], "processed": [10]}


def test_process_task_dispatches_summary_only(monkeypatch):
    worker = _import_worker_with_stubs(monkeypatch)
    task = SimpleNamespace(id=1, task_type="summary", parameters={"lesson_id": 42})

    calls = {"summary": 0, "brief": 0, "status_updates": [], "lesson_statuses": []}

    monkeypatch.setattr(
        worker,
        "update_task_status",
        lambda _session, _task, status, **_kwargs: calls["status_updates"].append(status),
    )
    monkeypatch.setattr(
        worker,
        "set_lesson_process_status",
        lambda _session, lesson_id, status: calls["lesson_statuses"].append((lesson_id, status)),
    )
    monkeypatch.setattr(
        worker,
        "process_summary_task",
        lambda _session, _task: calls.__setitem__("summary", calls["summary"] + 1),
    )
    monkeypatch.setattr(
        worker,
        "process_brief_task",
        lambda _session, _task: calls.__setitem__("brief", calls["brief"] + 1),
    )

    worker.process_task(SimpleNamespace(), task)

    assert calls["summary"] == 1
    assert calls["brief"] == 0
    assert calls["status_updates"] == ["running"]
    assert calls["lesson_statuses"] == [(42, "summary"), (42, None)]


def test_process_task_dispatches_brief_only(monkeypatch):
    worker = _import_worker_with_stubs(monkeypatch)
    task = SimpleNamespace(id=2, task_type="brief", parameters={"lesson_id": 77})

    calls = {"summary": 0, "brief": 0, "status_updates": [], "lesson_statuses": []}

    monkeypatch.setattr(
        worker,
        "update_task_status",
        lambda _session, _task, status, **_kwargs: calls["status_updates"].append(status),
    )
    monkeypatch.setattr(
        worker,
        "set_lesson_process_status",
        lambda _session, lesson_id, status: calls["lesson_statuses"].append((lesson_id, status)),
    )
    monkeypatch.setattr(
        worker,
        "process_summary_task",
        lambda _session, _task: calls.__setitem__("summary", calls["summary"] + 1),
    )
    monkeypatch.setattr(
        worker,
        "process_brief_task",
        lambda _session, _task: calls.__setitem__("brief", calls["brief"] + 1),
    )

    worker.process_task(SimpleNamespace(), task)

    assert calls["summary"] == 0
    assert calls["brief"] == 1
    assert calls["status_updates"] == ["running"]
    assert calls["lesson_statuses"] == [(77, "summary"), (77, None)]


def test_calculate_estimated_cost_applies_flex_ratio_only_when_confirmed(monkeypatch):
    worker = _import_worker_with_stubs(monkeypatch)
    preset = SimpleNamespace(
        provider="openrouter",
        model_id="openai/gpt-5",
        cost_input_per_m_tokens=10.0,
        cost_output_per_m_tokens=20.0,
        flex_cost_ratio=0.5,
    )
    monkeypatch.setattr(
        worker,
        "_build_pricing_map",
        lambda _session: {("openrouter", "openai/gpt-5"): preset},
    )

    result = worker._calculate_estimated_cost(
        SimpleNamespace(),
        {
            "model_usage": {
                "openrouter::openai/gpt-5::flex": {
                    "provider": "openrouter",
                    "model": "openai/gpt-5",
                    "service_tier": "flex",
                    "input_tokens": 1_000_000,
                    "output_tokens": 1_000_000,
                    "total_tokens": 2_000_000,
                },
                "openrouter::openai/gpt-5::default": {
                    "provider": "openrouter",
                    "model": "openai/gpt-5",
                    "service_tier": "default",
                    "input_tokens": 1_000_000,
                    "output_tokens": 0,
                    "total_tokens": 1_000_000,
                },
            }
        },
    )

    assert result["estimated_cost_usd"] == 25.0
    flex_row = result["estimated_cost_breakdown"][0]
    default_row = result["estimated_cost_breakdown"][1]
    assert flex_row["flex_used"] is True
    assert flex_row["base_estimated_cost_usd"] == 30.0
    assert flex_row["estimated_cost_usd"] == 15.0
    assert default_row["flex_used"] is False
    assert default_row["estimated_cost_usd"] == 10.0
