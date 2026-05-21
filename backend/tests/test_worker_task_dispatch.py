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

    fake_llm_utils = types.ModuleType("services.llm_utils")
    fake_llm_utils.get_token_usage_tracker = lambda: {}
    fake_llm_utils.reset_token_usage_tracker = lambda: None
    monkeypatch.setitem(sys.modules, "services.llm_utils", fake_llm_utils)

    fake_memory_usage = types.ModuleType("memory_usage")
    fake_memory_usage.format_memory_mb = lambda _value: "0 MB"
    fake_memory_usage.get_rss_memory_mb = lambda: 0.0
    monkeypatch.setitem(sys.modules, "memory_usage", fake_memory_usage)

    sys.modules.pop("worker", None)
    return importlib.import_module("worker")


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
