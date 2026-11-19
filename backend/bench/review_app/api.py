"""FastAPI app of the review UI: JSON API under /api, the Vue single page app under /."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from bench.review_app import data

STATIC_DIR = Path(__file__).parent / "static"
NODE_MODULES = Path(__file__).resolve().parents[3] / "frontend" / "node_modules"
# Served from the frontend dependencies when installed, else from a CDN.
VENDOR = {
    "vue.js": (NODE_MODULES / "vue" / "dist" / "vue.esm-browser.prod.js",
               "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js"),
    "marked.js": (NODE_MODULES / "marked" / "lib" / "marked.esm.js",
                  "https://unpkg.com/marked@11/lib/marked.esm.js"),
}

app = FastAPI(title="Bench review", docs_url="/api/docs", openapi_url="/api/openapi.json")


def _call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except data.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/campaigns")
def campaigns():
    return data.campaigns_list()


@app.get("/api/campaigns/{stem}")
def campaign(stem: str):
    return _call(data.dashboard, stem)


@app.get("/api/campaigns/{stem}/steps/{step}")
def step(stem: str, step: str):
    return _call(data.step_detail, stem, step)


@app.get("/api/campaigns/{stem}/steps/{step}/lessons/{lesson}")
def lesson(stem: str, step: str, lesson: str, candidates: Optional[str] = Query(None),
           repeat: Optional[int] = Query(None)):
    keys = [c for c in candidates.split(",") if c] if candidates else None
    return _call(data.lesson_detail, stem, step, lesson, keys, repeat)


@app.get("/vendor/{name}")
def vendor(name: str):
    if name not in VENDOR:
        raise HTTPException(status_code=404)
    local, cdn = VENDOR[name]
    if local.is_file():
        return FileResponse(local, media_type="text/javascript")
    return RedirectResponse(cdn)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


class _RevalidatedStaticFiles(StaticFiles):
    """app.js / style.css change often: the browser must revalidate them instead of reusing its cache."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", _RevalidatedStaticFiles(directory=STATIC_DIR), name="static")
