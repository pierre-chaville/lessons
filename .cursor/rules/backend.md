# Backend Cursor Rules — Torah Lessons Transcription Platform

## Project Overview

FastAPI backend for a Torah lessons transcription platform. The app transcribes audio lessons (MP3), generates edited long-form versions, extracts Sefaria sources, and produces summaries. Invitation-only, role-based access. Task processing is managed via a database-backed task queue.

## Tech Stack

- **Framework**: FastAPI (async where possible)
- **ORM**: SQLModel (SQLAlchemy + Pydantic hybrid)
- **Database**: PostgreSQL
- **Auth**: Clerk (JWT verification, roles: reader, editor, publisher, admin)
- **Storage**: Cloudflare R2 (S3-compatible) for audio files
- **External APIs**: OpenAI, Anthropic (transcription, LLM editing, summarization)
- **Hosting**: Render.com
- **Task processing**: DB-backed task table (no Celery/Redis)

## Project Structure

```
app/
├── main.py                  # FastAPI app, lifespan, middleware
├── config.py                # Settings via pydantic-settings (BaseSettings)
├── database.py              # Engine, session factory, get_session dependency
├── models/                  # SQLModel table models
│   ├── lesson.py
│   ├── task.py
│   ├── source.py
│   └── ...
├── schemas/                 # Pydantic request/response schemas (non-table models)
│   ├── lesson.py
│   ├── task.py
│   └── ...
├── routers/                 # APIRouter modules grouped by domain
│   ├── lessons.py
│   ├── tasks.py
│   ├── sources.py
│   └── admin.py
├── dependencies/            # Reusable Depends() functions
│   ├── auth.py              # Clerk JWT verification, role checks
│   ├── db.py                # Session dependency (if separated)
│   └── pagination.py
├── services/                # Business logic layer
│   ├── transcription.py     # Calls to Deepgram/OpenAI Whisper
│   ├── edition.py           # LLM-based lesson editing
│   ├── summary.py           # LLM-based summarization
│   ├── sefaria.py           # Sefaria API integration & source extraction
│   ├── storage.py           # R2/S3 upload/download
│   └── task_runner.py       # Task lifecycle: pick, execute, update status
├── utils/                   # Pure helpers (no app dependencies)
│   ├── text.py
│   ├── prompts.py           # LLM prompt templates
│   └── retry.py
├── migrations/              # Alembic migrations
└── tests/
```

## Code Style & Conventions

### General

- Python 3.12+. Use modern syntax: `X | None` instead of `Optional[X]`, `list[str]` not `List[str]`.
- All code, comments, docstrings, and variable names in **English**.
- Lesson content, prompts, and user-facing strings may be in **French or Hebrew** — that's expected.
- Use `async def` for all route handlers and any I/O-bound service functions (DB queries, HTTP calls, file ops).
- Use `def` (sync) only for pure computation with no I/O.
- Never use `time.sleep()` — use `asyncio.sleep()` if needed.
- Prefer `httpx.AsyncClient` over `requests` for all outbound HTTP calls.

### Naming

- Files and modules: `snake_case.py`
- Classes: `PascalCase`
- Functions, variables, parameters: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- SQLModel table models: singular noun (`Lesson`, `Task`, not `Lessons`)
- Router prefixes: plural (`/lessons`, `/tasks`, `/sources`)

### Type Hints

- **Always** type function signatures (params + return type).
- Use SQLModel field types with explicit `Field()` for table columns.
- Use Pydantic models (in `schemas/`) for request bodies and response models — don't expose table models directly in API responses unless they match exactly.

### Error Handling

- Raise `HTTPException` with appropriate status codes in routers only.
- Services should raise domain-specific exceptions (custom exception classes in `app/exceptions.py`) — routers catch and translate to HTTP errors.
- Never return bare dicts from endpoints — always use typed response models.
- Use `status_code=status.HTTP_201_CREATED` (not magic numbers) for non-200 responses.

## SQLModel & Database

### Models

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import uuid4, UUID

class Lesson(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str
    rabbi: str | None = None
    status: str = Field(default="draft")  # draft, published, archived
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- Use `UUID` primary keys (not auto-increment integers).
- Always include `created_at` and `updated_at` timestamps.
- Use `Field(index=True)` for columns frequently used in WHERE/ORDER BY.
- Relationships: use SQLModel `Relationship()` with explicit `back_populates`.

### Sessions

- Use `async_sessionmaker` with `AsyncSession`.
- Provide session via `Depends(get_session)` — never create sessions manually in services.
- Pass the session explicitly to service functions; services never import the session factory directly.
- Use `session.exec(select(...))` — not raw `session.query()`.

### Migrations

- Use Alembic with async support.
- Always review auto-generated migrations before applying.
- One migration per logical schema change.

## Task Processing

Tasks represent async work (transcription, edition, summary extraction). They are stored in a `Task` table and processed by a background worker (or endpoint-triggered runner).

```python
class Task(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    lesson_id: UUID = Field(foreign_key="lesson.id", index=True)
    type: str          # "transcription", "edition", "summary", "source_extraction"
    status: str        # "pending", "running", "completed", "failed"
    error: str | None = None
    result_metadata: dict | None = Field(default=None, sa_column_kwargs={"type_": JSON})
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

- Task creation is **always separate** from task execution.
- A route creates a task with status `pending`, then returns immediately.
- The task runner picks pending tasks (SELECT ... FOR UPDATE SKIP LOCKED pattern if concurrent), marks `running`, executes, then marks `completed` or `failed`.
- Always store errors in the `error` field — never silently swallow exceptions in task processing.
- Task types should be defined as a `StrEnum` or `Literal` type, not free-form strings.

## Authentication & Authorization

### Clerk JWT Verification

```python
# dependencies/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> ClerkUser:
    """Verify Clerk JWT and return user info."""
    token = credentials.credentials
    # Verify with Clerk JWKS / local verification
    # Extract: user_id, email, role from JWT claims
    ...
```

### Roles

Roles and per-resource permissions are defined in `.cursor/rules/access.md` — that file is the single source of truth for both frontend and backend. Always consult it when adding or modifying endpoints.

Implement a `require_role(*allowed_roles)` dependency factory:

```python
def require_role(*roles: str):
    async def checker(user: ClerkUser = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker
```

Every endpoint must include the appropriate `require_role()` call matching the permission matrix in `access.md`.

## External API Integrations

### LLM Calls (OpenAI / Anthropic) via LangChain

- **All LLM calls go through LangChain** — never use OpenAI/Anthropic SDKs directly.
- Use `ChatOpenAI` / `ChatAnthropic` from `langchain-openai` / `langchain-anthropic`.
- **Prefer structured output** via `.with_structured_output(PydanticModel)` whenever the response has a known schema. Define output schemas as Pydantic models in `schemas/` or co-located with the service.

```python
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

class ExtractedSources(BaseModel):
    """Sources extracted from a Torah lesson."""
    sources: list[SourceRef] = Field(description="List of identified Sefaria references")
    confidence: float = Field(description="Overall extraction confidence 0-1")

llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
chain = llm.with_structured_output(ExtractedSources)
result: ExtractedSources = await chain.ainvoke(messages)
```

- **When to use structured output**: source extraction, metadata extraction, classification, any response parsed programmatically.
- **When to use plain text output**: long-form edition, summaries, any content displayed as-is to users.
- Centralize LLM calls in service functions — never call LangChain from routers.
- Store prompt templates in `utils/prompts.py` as `ChatPromptTemplate` or string constants.
- Use `langchain_core.prompts.ChatPromptTemplate` for multi-variable prompts.
- Always pass `temperature` and `model` explicitly when instantiating chat models — no implicit defaults.
- Use `ainvoke()` / `astream()` (async) — never `invoke()` / `stream()` (sync) in async context.
- Implement retry with exponential backoff for transient errors (429, 500, 503) — use LangChain's built-in `.with_retry()` or a custom wrapper.
- Log token usage (input/output tokens) for cost tracking — access via `response.response_metadata` or callbacks.
- Use streaming (`astream()`) only when the response is forwarded to the frontend in real-time.
- Keep LangChain chains simple — prefer `prompt | llm.with_structured_output(Schema)` over complex LCEL chains unless justified.
- Pin LangChain package versions in requirements — the API surface changes frequently.

### Sefaria API

- Use `httpx.AsyncClient` with a base URL (`https://www.sefaria.org/api/`).
- Cache reference lookups where possible (sources rarely change).
- Handle Hebrew and English reference formats.

### Cloudflare R2 (S3)

- Use `boto3` or `aioboto3` with S3-compatible endpoint.
- Generate presigned URLs for frontend uploads/downloads — don't proxy large files through the backend.
- Organize keys: `lessons/{lesson_id}/audio.mp3`, `lessons/{lesson_id}/transcript.json`.
- Set appropriate content types on upload.

## API Design

### Routes

- Group by domain: `/api/v1/lessons`, `/api/v1/tasks`, `/api/v1/sources`.
- Use `APIRouter` with `prefix` and `tags`.
- Keep route handlers thin — delegate to services.
- Return explicit `response_model` on every endpoint.
- Use `status_code=201` for creation endpoints.
- Use path params for resource identifiers: `/lessons/{lesson_id}`.
- Use query params for filtering/pagination: `?status=published&page=1&per_page=20`.

### Pagination

- Offset-based pagination with `page` and `per_page` (default 20, max 100).
- Return total count in response for frontend pagination UI.

```python
class PaginatedResponse(SQLModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
```

### Response Consistency

- Success responses: return the resource or list with metadata.
- Error responses: `{"detail": "Human-readable message"}` (FastAPI default for HTTPException).
- Never return `null` for collection endpoints — return empty list `[]`.

## Configuration

- Use `pydantic-settings` `BaseSettings` with `.env` file support.
- Prefix env vars: `DATABASE_URL`, `CLERK_SECRET_KEY`, `R2_ACCESS_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- Never hardcode secrets or API keys.
- Separate settings for dev/staging/prod via `ENVIRONMENT` env var if needed.

## Logging

- Use `structlog` or Python's `logging` with JSON formatter for production.
- Log at service boundaries: task started/completed/failed, API calls made, auth failures.
- Never log secrets, tokens, or full request bodies containing sensitive data.
- Include `lesson_id`, `task_id`, `user_id` in log context where available.

## Testing

- Use `pytest` with `pytest-asyncio`.
- Use `httpx.AsyncClient` with `ASGITransport` for integration tests.
- Mock external APIs (OpenAI, Anthropic, Sefaria, R2) in tests — never make real calls.
- Test auth: include valid/invalid/missing JWT scenarios.
- Test task state transitions: pending → running → completed/failed.
- Separate unit tests (services) from integration tests (routes).

## Common Patterns

### Service function signature

```python
async def transcribe_lesson(
    lesson_id: UUID,
    session: AsyncSession,
    storage: StorageService,
) -> TranscriptionResult:
    """Download audio from R2, send to transcription API, store result."""
    ...
```

Services receive dependencies as parameters — they are not classes with injected state (unless complexity justifies it).

### Background task trigger pattern

```python
@router.post("/lessons/{lesson_id}/transcribe", status_code=201)
async def request_transcription(
    lesson_id: UUID,
    user: ClerkUser = Depends(require_role("editor", "admin")),
    session: AsyncSession = Depends(get_session),
) -> TaskRead:
    lesson = await get_lesson_or_404(lesson_id, session)
    task = Task(lesson_id=lesson.id, type="transcription", status="pending")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    # Optionally trigger the runner via BackgroundTasks
    return task
```

## Do NOT

- Do not use `from __future__ import annotations` — it breaks SQLModel in some versions.
- Do not use global mutable state (module-level dicts, lists) for anything — use DB or config.
- Do not catch broad `Exception` without re-raising or logging.
- Do not use `*args, **kwargs` in route handlers or service functions.
- Do not store full transcription/edition text in the task table — store it in the lesson or a dedicated content table.
- Do not call external APIs synchronously (blocking the event loop).
- Do not trust user-supplied data from JWT without verification — always validate the token signature.

## Deployment (Render.com)

- Use a `Dockerfile` or `render.yaml` for reproducible builds.
- Run with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Set `--workers 1` unless the task runner is process-safe (use DB locking).
- Health check endpoint: `GET /health` returning `{"status": "ok"}`.
- Run Alembic migrations in the build/release phase, not at app startup.
