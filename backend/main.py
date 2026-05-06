"""FastAPI application — app setup, middleware, and router registration."""

import os
import threading
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer

from auth import require_auth
from routers import courses, themes, lessons, upload, tasks, config, search, users, sefaria_cache, webhooks, audit
import worker as worker_module

bearer_scheme = HTTPBearer()

_worker_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the background task worker on startup; stop it on shutdown."""
    global _worker_thread
    _worker_thread = worker_module.start_worker_thread()
    yield
    # Signal the worker to stop and give it up to 30 s to finish the current task.
    worker_module.should_stop = True
    if _worker_thread is not None:
        _worker_thread.join(timeout=30)


app = FastAPI(
    title="Lessons Manager API",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(require_auth)],
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "Bearer token authentication using Clerk JWTs.",
        }
    ],
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})
    openapi_schema["components"]["securitySchemes"]["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    openapi_schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ── CORS ──────────────────────────────────────────────────────────────────────

allowed_origins = [
    origin.strip()
    for origin in (os.getenv("ALLOWED_ORIGINS") or "").split(",")
    if origin.strip()
]
if not allowed_origins:
    allowed_origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(courses.router)
app.include_router(themes.router)
app.include_router(lessons.router)
app.include_router(upload.router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(search.router)
app.include_router(users.router)
app.include_router(sefaria_cache.router)
app.include_router(webhooks.router)
app.include_router(audit.router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Lessons Manager API"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/auth/me", tags=["Authentication"])
def auth_me(claims: Dict[str, Any] = Depends(require_auth)):
    """Return the current authenticated user's token claims."""
    return {"claims": claims}
