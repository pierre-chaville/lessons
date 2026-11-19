"""Sefaria texts for the verification of the references added by the models (faithfulness).

Same API as the app (services/sources.py), without its database: answers are cached in
results/sefaria_cache.json (also the failures, so that a missing reference is asked once).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

import httpx

from bench.dataset import BENCH_DIR

API = "https://www.sefaria.org/api/texts"
CACHE_PATH = BENCH_DIR / "results" / "sefaria_cache.json"
MAX_CHARS = 3000

_lock = threading.Lock()
_cache: Optional[dict] = None

_REF_RE = re.compile(r"^\s*(.+?)[\s.]+(\d+(?:[:.,]\s*\d+)*(?:\s*[-–]\s*\d+(?:[:.]\d+)?)?)\s*$")


def slug(ref: str) -> Optional[str]:
    """`Hosea 14:3` / `I Samuel 3, 4-6` -> `Hosea.14.3` / `I_Samuel.3.4-6` (None if not a reference)."""
    match = _REF_RE.match(ref or "")
    if not match:
        return None
    book = re.sub(r"\s+", "_", match.group(1).strip())
    numbers = re.sub(r"\s+", "", match.group(2)).replace(":", ".").replace(",", ".").replace("–", "-")
    return f"{book}.{numbers}"


def _flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.is_file() else {}
    return _cache


def _save() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch(ref: str, timeout: float = 30.0) -> dict:
    """{"slug", "found", "ref" (canonical), "he", "en", "error"} for a reference (cached)."""
    key = slug(ref)
    if key is None:
        return {"slug": None, "found": False, "error": f"not a reference: {ref!r}"}
    with _lock:
        cached = _load().get(key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(f"{API}/{key}", params={"context": 0}, timeout=timeout, follow_redirects=True)
        data = response.json() if response.status_code == 200 else {"error": f"HTTP {response.status_code}"}
    except (httpx.HTTPError, ValueError) as exc:
        return {"slug": key, "found": False, "error": f"{type(exc).__name__}: {exc}"}  # not cached: may be transient
    he = _strip_html(_flatten(data.get("he")))[:MAX_CHARS]
    en = _strip_html(_flatten(data.get("text")))[:MAX_CHARS]
    result = {
        "slug": key,
        "found": bool(he or en) and not data.get("error"),
        "ref": data.get("ref"),
        "he": he,
        "en": en,
        "error": data.get("error"),
    }
    with _lock:
        _load()[key] = result
        _save()
    return result
