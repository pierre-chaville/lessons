"""LLM completion of glossary entries (fake structured-output model, SQLite)."""

from collections.abc import Iterator
import json

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import auth
import crud
import database
from config import DEFAULT_CONFIG, normalize_config
from models import Task
from routers import glossary as glossary_router
from routers import tasks as tasks_router
from schemas.glossary import GlossaryCompletion, GlossaryCompletionBatch
from services import glossary_completion as service

TESHUVA = "תְּשׁוּבָה"
HESSED = "חֶסֶד"
SHABBAT = "שַׁבָּת"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


class FakeLLM:
    """Answers each batch from ``answers`` (hebrew -> translit); records prompts."""

    def __init__(self, answers: dict[str, str], fail: bool = False) -> None:
        self.answers = answers
        self.fail = fail
        self.prompts: list[str] = []
        self.schemas: list[type] = []

    def with_structured_output(self, schema: type, method: str | None = None) -> "FakeLLM":
        self.schemas.append(schema)
        return self

    async def ainvoke(self, prompt: str) -> GlossaryCompletionBatch:
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("provider down")
        payload = json.loads(prompt[prompt.index("["):])
        return GlossaryCompletionBatch(
            entries=[
                GlossaryCompletion(
                    id=item["id"],
                    translit=self.answers.get(item["hebrew"], ""),
                    aliases=["alias", self.answers.get(item["hebrew"], "")],
                    type="term",
                    case_flag="lower",
                    translation="traduction",
                    sefaria_title=None,
                    sefaria_ref=None,
                )
                for item in payload
            ]
        )


def _patch(monkeypatch: pytest.MonkeyPatch, llm: FakeLLM, prompt: str = "Complete.") -> None:
    config = {"glossary": {"model_preset_id": None, "prompt": prompt, "max_tokens": 500}}
    monkeypatch.setattr(service, "load_config", lambda: config)
    monkeypatch.setattr(service, "get_llm_model", lambda **kwargs: llm)
    monkeypatch.setattr(service, "INITIAL_RETRY_DELAY", 0)


def test_config_has_normalized_glossary_section() -> None:
    config = normalize_config({"glossary": {"model_preset_id": "3", "max_tokens": "x"}})
    assert config["glossary"]["model_preset_id"] == 3
    assert config["glossary"]["max_tokens"] == DEFAULT_CONFIG["glossary"]["max_tokens"]
    assert config["glossary"]["prompt"] == DEFAULT_CONFIG["glossary"]["prompt"]


@pytest.mark.anyio
async def test_completes_only_entries_without_translit(session, monkeypatch) -> None:
    crud.create_glossary_entry(session, {"hebrew": TESHUVA, "translit": "techouva"})
    crud.create_glossary_entry(
        session, {"hebrew": HESSED, "status": "auto", "context_paragraph": f"le {HESSED} de Dieu"}
    )
    crud.create_glossary_entry(session, {"hebrew": SHABBAT, "status": "rejected"})
    llm = FakeLLM({HESSED: "'hessed"})
    _patch(monkeypatch, llm, prompt="Complete these.")

    report = await service.complete_glossary_entries_async(session)

    assert report == {"pending": 1, "completed": 1, "skipped": 0, "failed_batches": 0}
    assert llm.schemas == [GlossaryCompletionBatch]
    assert llm.prompts[0].startswith("Complete these.")
    assert f"le {HESSED} de Dieu" in llm.prompts[0]
    assert TESHUVA not in llm.prompts[0] and SHABBAT not in llm.prompts[0]
    hessed = crud.get_glossary_entry_by_hebrew_norm(session, HESSED)
    assert hessed.translit == "'hessed"
    assert hessed.aliases == ["alias"]
    assert hessed.translation == "traduction"
    assert hessed.status == "auto"


@pytest.mark.anyio
async def test_empty_translit_answers_are_skipped(session, monkeypatch) -> None:
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    _patch(monkeypatch, FakeLLM({}))
    report = await service.complete_glossary_entries_async(session)
    assert report["completed"] == 0 and report["skipped"] == 1
    assert crud.get_glossary_entry_by_hebrew_norm(session, HESSED).translit is None


@pytest.mark.anyio
async def test_batches_and_raises_when_every_batch_fails(session, monkeypatch) -> None:
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    llm = FakeLLM({}, fail=True)
    _patch(monkeypatch, llm)
    with pytest.raises(RuntimeError):
        await service.complete_glossary_entries_async(session)
    assert len(llm.prompts) == service.MAX_RETRIES


@pytest.mark.anyio
async def test_empty_prompt_is_a_config_error(session, monkeypatch) -> None:
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    _patch(monkeypatch, FakeLLM({}), prompt="  ")
    with pytest.raises(service.GlossaryCompletionConfigError):
        await service.complete_glossary_entries_async(session)


def test_enqueue_reuses_active_task_and_skips_when_nothing_to_do(session) -> None:
    assert service.enqueue_glossary_completion(session) is None
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    first = service.enqueue_glossary_completion(session)
    second = service.enqueue_glossary_completion(session)
    assert first is not None and first == second
    tasks = session.exec(select(Task)).all()
    assert [task.task_type for task in tasks] == [service.GLOSSARY_TASK_TYPE]


def _client(session: Session, role: str) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(glossary_router.router)
    app.include_router(tasks_router.router)
    app.dependency_overrides[auth.require_auth] = lambda: {"sub": "user_1", "role": role}
    app.dependency_overrides[database.get_session] = lambda: session
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_complete_endpoint_roles_and_payload(session) -> None:
    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    async with _client(session, "editor") as client:
        denied = await client.post("/glossary/complete")
        denied_generic = await client.post("/tasks", json={"task_type": "glossary"})
    async with _client(session, "publisher") as client:
        launched = await client.post("/glossary/complete")
    assert denied.status_code == 403
    assert denied_generic.status_code == 403
    assert launched.status_code == 200
    body = launched.json()
    assert body["pending_entries"] == 1 and isinstance(body["task_id"], int)


@pytest.mark.anyio
async def test_completion_status_endpoint(session) -> None:
    async with _client(session, "publisher") as client:
        empty = (await client.get("/glossary/complete/status")).json()
    assert empty == {
        "pending_entries": 0, "task_id": None, "task_status": None,
        "task_error": None, "task_result": None,
    }

    crud.create_glossary_entry(session, {"hebrew": HESSED, "status": "auto"})
    task_id = service.enqueue_glossary_completion(session)
    async with _client(session, "editor") as client:
        denied = await client.get("/glossary/complete/status")
    async with _client(session, "publisher") as client:
        queued = (await client.get("/glossary/complete/status")).json()
    assert denied.status_code == 403
    assert queued["pending_entries"] == 1
    assert queued["task_id"] == task_id and queued["task_status"] == "pending"
