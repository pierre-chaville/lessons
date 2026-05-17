from datetime import datetime
import sys
from types import SimpleNamespace
import types
from enum import Enum

from fastapi import FastAPI
import httpx
import pytest

# Lightweight stub so importing auth/routers does not require jose in minimal test envs.
if "jose" not in sys.modules:
    fake_jose = types.ModuleType("jose")
    fake_jose.jwt = types.SimpleNamespace()
    sys.modules["jose"] = fake_jose

if "database" not in sys.modules:
    fake_database = types.ModuleType("database")
    fake_database.engine = None
    fake_database.create_db_and_tables = lambda: None
    fake_database.get_session = lambda: None
    sys.modules["database"] = fake_database

if "services" not in sys.modules:
    services_pkg = types.ModuleType("services")
    services_pkg.__path__ = []  # mark as package

    services_lessons = types.ModuleType("services.lessons")
    services_exports = types.ModuleType("services.exports")
    services_audit = types.ModuleType("services.audit")
    services_versioning = types.ModuleType("services.versioning")

    class _FakeContentType(str, Enum):
        TITLE = "title"
        CORRECTED_TRANSCRIPT = "corrected_transcript"
        EDITED_TRANSCRIPT = "edited_transcript"
        BRIEF = "brief"
        SUMMARY = "summary"

    services_versioning.ContentType = _FakeContentType
    services_versioning.compute_diff = lambda *args, **kwargs: {}
    services_versioning.get_version = lambda *args, **kwargs: None
    services_versioning.list_versions = lambda *args, **kwargs: []
    services_versioning.restore_version = lambda *args, **kwargs: None
    services_versioning.seal_current_version = lambda *args, **kwargs: None

    services_audit.get_lesson_audit_log = lambda *args, **kwargs: []

    services_exports.document_bytes_to_markdown = lambda data, filename: data.decode("utf-8", errors="ignore")
    services_exports.extract_markdown_main_section = lambda markdown: str(markdown or "").strip()

    def _fake_transcript_markdown_to_segments(markdown):
        rows = []
        for idx, line in enumerate(str(markdown or "").splitlines()):
            text = line.strip().removeprefix("-").strip()
            if text:
                rows.append({"start": float(idx), "end": float(idx + 1), "text": text})
        return rows

    services_exports.transcript_markdown_to_segments = _fake_transcript_markdown_to_segments

    services_pkg.lessons = services_lessons
    services_pkg.exports = services_exports
    sys.modules["services"] = services_pkg
    sys.modules["services.lessons"] = services_lessons
    sys.modules["services.exports"] = services_exports
    sys.modules["services.audit"] = services_audit
    sys.modules["services.versioning"] = services_versioning

from routers import lessons as lessons_router


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _lesson_response_payload(
    *,
    summary: str | None = None,
    corrected_transcript: list[dict] | None = None,
    edited_transcript: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(**{
        "id": 1,
        "hashid": "abc123",
        "title": "Test Lesson",
        "filename": "lesson.wav",
        "course_id": None,
        "date": datetime(2026, 1, 1).isoformat(),
        "duration": 120.0,
        "transcript": [],
        "corrected_transcript": corrected_transcript,
        "edited_transcript": edited_transcript,
        "brief": None,
        "summary": summary,
        "status": "draft",
        "process_status": None,
        "theme_ids": [],
        "themes": [],
        "course": None,
        "sources": [],
        "editors": [],
        "transcript_metadata": None,
        "correction_metadata": None,
        "summary_metadata": None,
        "edited_metadata": None,
    })


def _build_client():
    app = FastAPI()
    app.include_router(lessons_router.router)
    app.dependency_overrides[lessons_router.require_auth] = lambda: {"sub": "user_1", "role": "admin"}
    app.dependency_overrides[lessons_router.get_session] = lambda: object()
    return app


@pytest.mark.anyio
async def test_import_summary_updates_content_and_realigns(monkeypatch):
    app = _build_client()
    lesson = SimpleNamespace(corrected_transcript=[], transcript=[])
    calls = {"realign_summary": 0}

    monkeypatch.setattr(lessons_router, "decode_id", lambda _: 1)
    monkeypatch.setattr(lessons_router.crud, "get_lesson", lambda _session, _lesson_id: lesson)
    monkeypatch.setattr(
        lessons_router.export_service,
        "document_bytes_to_markdown",
        lambda _bytes, filename=None: f"# Preface\n\n<!-- MARKER:section-start -->\n\nImported summary\n<!-- MARKER:section-end -->\n{filename}",
    )
    monkeypatch.setattr(
        lessons_router.export_service,
        "extract_markdown_main_section",
        lambda _markdown: "Imported summary",
    )

    def fake_update(_lesson_id, lesson_data, _session, assigned_by=None):
        assert lesson_data.summary == "Imported summary"
        assert assigned_by == "user_1"
        return _lesson_response_payload(
            summary=lesson_data.summary,
            edited_transcript={
                "markdown": "Edited text",
                "sources": [],
                "alignment": [],
                "transcript_hash": None,
                "markdown_hash": None,
                "aligned_at": None,
            },
        )

    def fake_realign_summary_alignment(*, lesson_id, session):
        assert lesson_id == 1
        assert session is not None
        calls["realign_summary"] += 1
        return _lesson_response_payload(summary="Imported summary", edited_transcript=None)

    monkeypatch.setattr(lessons_router.lesson_service, "update_lesson_data", fake_update, raising=False)
    monkeypatch.setattr(
        lessons_router.lesson_service,
        "realign_summary_alignment",
        fake_realign_summary_alignment,
        raising=False,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/lessons/abc123/imports/summary",
            files={"file": ("summary.md", b"content", "text/markdown")},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"] == "Imported summary"
    assert calls["realign_summary"] == 1


@pytest.mark.anyio
async def test_import_edited_triggers_edited_then_summary_realign(monkeypatch):
    app = _build_client()
    lesson = SimpleNamespace(corrected_transcript=[{"start": 0.0, "end": 1.0, "text": "A"}], transcript=[])
    calls = {"realign_edited": 0, "realign_summary": 0}

    monkeypatch.setattr(lessons_router, "decode_id", lambda _: 1)
    monkeypatch.setattr(lessons_router.crud, "get_lesson", lambda _session, _lesson_id: lesson)
    monkeypatch.setattr(
        lessons_router.export_service,
        "document_bytes_to_markdown",
        lambda _bytes, filename=None: "Imported edited markdown",
    )

    def fake_update(_lesson_id, lesson_data, _session, assigned_by=None):
        assert getattr(lesson_data.edited_transcript, "markdown", None) == "Imported edited markdown"
        assert assigned_by == "user_1"
        return _lesson_response_payload(summary="has summary")

    def fake_realign_edited(*, lesson_id, session, actor=None):
        assert lesson_id == 1
        assert actor == {"sub": "user_1", "role": "admin"}
        assert session is not None
        calls["realign_edited"] += 1
        return _lesson_response_payload(summary="has summary")

    def fake_realign_summary_alignment(*, lesson_id, session):
        assert lesson_id == 1
        assert session is not None
        calls["realign_summary"] += 1
        return _lesson_response_payload(summary="has summary")

    monkeypatch.setattr(lessons_router.lesson_service, "update_lesson_data", fake_update, raising=False)
    monkeypatch.setattr(
        lessons_router.lesson_service,
        "realign_edited_markdown",
        fake_realign_edited,
        raising=False,
    )
    monkeypatch.setattr(
        lessons_router.lesson_service,
        "realign_summary_alignment",
        fake_realign_summary_alignment,
        raising=False,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/lessons/abc123/imports/edited",
            files={
                "file": (
                    "edited.docx",
                    b"fake-docx-binary",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls["realign_edited"] == 1
    assert calls["realign_summary"] == 1


@pytest.mark.anyio
async def test_import_transcript_parses_lines_and_updates_corrected_transcript(monkeypatch):
    app = _build_client()
    lesson = SimpleNamespace(corrected_transcript=[], transcript=[])
    captured: dict = {}

    monkeypatch.setattr(lessons_router, "decode_id", lambda _: 1)
    monkeypatch.setattr(lessons_router.crud, "get_lesson", lambda _session, _lesson_id: lesson)
    monkeypatch.setattr(
        lessons_router.export_service,
        "document_bytes_to_markdown",
        lambda _bytes, filename=None: "- [00:01 - 00:03] First line\n- Plain fallback",
    )
    monkeypatch.setattr(
        lessons_router.export_service,
        "transcript_markdown_to_segments",
        lambda _markdown: [
            {"start": 1.0, "end": 3.0, "text": "First line"},
            {"start": 3.0, "end": 4.0, "text": "Plain fallback"},
        ],
    )

    def fake_update(_lesson_id, lesson_data, _session, assigned_by=None):
        captured["corrected_transcript"] = lesson_data.corrected_transcript
        assert assigned_by == "user_1"
        return _lesson_response_payload(
            corrected_transcript=lesson_data.corrected_transcript,
            edited_transcript=None,
        )

    monkeypatch.setattr(lessons_router.lesson_service, "update_lesson_data", fake_update, raising=False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/lessons/abc123/imports/transcript",
            files={"file": ("transcript.md", b"content", "text/markdown")},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [
        {"start": float(seg.start), "end": float(seg.end), "text": str(seg.text)}
        for seg in captured["corrected_transcript"]
    ] == [
        {"start": 1.0, "end": 3.0, "text": "First line"},
        {"start": 3.0, "end": 4.0, "text": "Plain fallback"},
    ]
