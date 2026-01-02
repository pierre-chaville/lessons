from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple


def _tokens(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio() * 100.0


def fuzzy_segment_score(query: str, segment_text: str) -> Tuple[float, bool]:
    """Return (score_0_to_100, exact_substring_match).

    - Exact match is case-insensitive substring match against the raw segment text.
    - Otherwise uses a sliding token-window similarity to allow fuzzy matching.
    """
    query_raw = (query or "").strip()
    if not query_raw:
        return 0.0, False

    seg_raw = segment_text or ""
    if not seg_raw.strip():
        return 0.0, False

    if query_raw.lower() in seg_raw.lower():
        return 100.0, True

    q_tokens = _tokens(query_raw)
    s_tokens = _tokens(seg_raw)
    if not q_tokens or not s_tokens:
        return 0.0, False

    q = " ".join(q_tokens)
    q_len = len(q_tokens)

    # Try a few window sizes around the query length.
    window_sizes = []
    for delta in (0, 1, -1, 2, -2, 3):
        size = q_len + delta
        if size >= 1:
            window_sizes.append(size)

    best = 0.0
    max_len = len(s_tokens)

    for window_size in window_sizes:
        if window_size > max_len:
            continue
        for i in range(0, max_len - window_size + 1):
            window = " ".join(s_tokens[i : i + window_size])
            best = max(best, _ratio(q, window))
            if best >= 95.0:
                return best, False

    # Also compare against the full segment as a fallback.
    best = max(best, _ratio(q, " ".join(s_tokens)))

    return best, False


def find_matching_segments(
    segments: Optional[Iterable[dict]],
    query: str,
    *,
    threshold: float = 72.0,
    max_matches: int = 50,
) -> List[dict]:
    """Return list of matched segment dicts with {start,end,text,score,exact}."""
    if not segments:
        return []

    q = (query or "").strip()
    if not q:
        return []

    matches: List[dict] = []

    for seg in segments:
        if not isinstance(seg, dict):
            continue

        text = seg.get("text") or ""
        score, exact = fuzzy_segment_score(q, text)
        if score >= threshold:
            matches.append(
                {
                    "start": float(seg.get("start") or 0.0),
                    "end": float(seg.get("end") or 0.0),
                    "text": text,
                    "score": float(score),
                    "exact": bool(exact),
                }
            )

    matches.sort(key=lambda m: (-m["score"], m["start"]))
    return matches[:max_matches]
