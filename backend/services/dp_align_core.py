import math
import re
import unicodedata
from collections import Counter
from typing import TypedDict

"""Core DP TF-IDF aligner for text-only inputs.

This module exposes a reusable function, `align_dp_texts`, that aligns edited
paragraph texts to transcript segment texts using dynamic programming over
contiguous windows.

Input contract:
- transcript: list[str] (one transcript segment text per item)
- edited: list[str] (one edited paragraph text per item)

Output contract:
- list of dict rows with keys:
    - start: None (timestamps are not available in this text-only core)
    - end: None
    - text: paragraph text
    - match_score: local transition score for selected span
    - source_start_index/source_end_index: matched transcript span indices
"""

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+")
NEG = float("-inf")


class AlignmentRow(TypedDict):
    start: float | None
    end: float | None
    text: str
    match_score: float
    source_start_index: int | None
    source_end_index: int | None


TfidfVector = dict[str, float]
Span = tuple[int | None, int | None, float]


def normalize_text(text: str) -> str:
    """Lowercase and strip diacritics to make token matching more robust."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def tokenize(text: str) -> list[str]:
    """Tokenize normalized text into alnum/apostrophe tokens."""
    return TOKEN_RE.findall(normalize_text(text))


def build_idf(transcript_texts: list[str], edited_texts: list[str]) -> dict[str, float]:
    """Build smoothed IDF values on combined transcript + edited corpora."""
    docs = transcript_texts + edited_texts
    n_docs = len(docs)
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(tokenize(doc)))

    return {
        term: math.log((1 + n_docs) / (1 + freq)) + 1.0 for term, freq in df.items()
    }


def build_para_vectors(
    edited: list[str], idf: dict[str, float]
) -> tuple[list[TfidfVector], list[float], list[int]]:
    """Convert edited paragraphs to TF-IDF vectors and precompute norms/lengths."""
    para_vecs: list[TfidfVector] = []
    para_norms: list[float] = []
    para_lens: list[int] = []

    for para_text in edited:
        counts = Counter(tokenize(para_text))
        para_lens.append(max(1, sum(counts.values())))

        vec: TfidfVector = {}
        norm_sq = 0.0
        for t, cnt in counts.items():
            w = idf.get(t, 0.0)
            if w == 0.0:
                continue
            v = float(cnt) * w
            vec[t] = v
            norm_sq += v * v

        para_vecs.append(vec)
        para_norms.append(math.sqrt(norm_sq))

    return para_vecs, para_norms, para_lens


def empty_output_rows(edited: list[str]) -> list[AlignmentRow]:
    """Create fallback output rows when alignment cannot be computed."""
    return [
        {
            "start": None,
            "end": None,
            "text": text,
            "match_score": 0.0,
            "source_start_index": None,
            "source_end_index": None,
        }
        for text in edited
    ]


def align_dp_texts(
    transcript: list[str],
    edited: list[str],
    max_window_segments: int = 40,
    length_penalty_strength: float = 0.6,
    require_full_coverage: bool = True,
) -> list[AlignmentRow]:
    """Align edited paragraphs to transcript segments using DP over contiguous windows.

    Returns one row per edited paragraph with source index span and local score.
    `start` and `end` are always None in this text-only core module.
    """
    n_paras = len(edited)
    n_segs = len(transcript)
    if n_paras == 0:
        return []
    if n_segs == 0:
        return empty_output_rows(edited)

    idf: dict[str, float] = build_idf(transcript, edited)

    seg_counts = [Counter(tokenize(text)) for text in transcript]
    seg_lens = [sum(c.values()) for c in seg_counts]
    para_vecs, para_norms, para_lens = build_para_vectors(edited, idf)

    # dp[i][j]: best score using first i paragraphs, consuming first j segments.
    # back[i][j]: best previous boundary k for that state.
    # local_score[i][j]: transition gain for chosen k -> j.
    dp: list[list[float]] = [[NEG] * (n_segs + 1) for _ in range(n_paras + 1)]
    back: list[list[int]] = [[-1] * (n_segs + 1) for _ in range(n_paras + 1)]
    local_score: list[list[float]] = [[NEG] * (n_segs + 1) for _ in range(n_paras + 1)]
    dp[0][0] = 0.0

    for i in range(1, n_paras + 1):
        para_vec = para_vecs[i - 1]
        para_norm = para_norms[i - 1]
        para_len = para_lens[i - 1]

        # Feasible j range keeps at least one segment for each remaining paragraph.
        j_lo = i
        j_hi = n_segs - (n_paras - i)
        if j_lo > j_hi:
            continue

        for j in range(j_lo, j_hi + 1):
            window_counts: Counter[str] = Counter()
            dot, norm_sq, window_len = 0.0, 0.0, 0
            best, best_k = NEG, -1

            k_lo = max(i - 1, j - max_window_segments)

            # Extend window leftward so each step adds segment k.
            # Candidate paragraph span is [k, j - 1].
            for k in range(j - 1, k_lo - 1, -1):
                window_len += seg_lens[k]

                # Incrementally update:
                # - window TF counts
                # - window norm (norm_sq)
                # - dot product with current paragraph vector
                for t, cnt in seg_counts[k].items():
                    w = idf.get(t, 0.0)
                    if w == 0.0:
                        continue

                    old = window_counts[t]
                    new = old + cnt
                    window_counts[t] = new

                    norm_sq += w * w * (new * new - old * old)

                    pv = para_vec.get(t)
                    if pv is not None:
                        dot += pv * w * cnt

                prev = dp[i - 1][k]
                if prev == NEG or norm_sq == 0.0 or para_norm == 0.0:
                    continue

                sim = dot / (para_norm * math.sqrt(norm_sq))
                ratio = window_len / para_len
                length_prior = math.exp(
                    -length_penalty_strength * abs(math.log(max(ratio, 1e-9)))
                )

                gain = sim * length_prior
                score = prev + gain

                if score > best:
                    best, best_k = score, k
                    local_score[i][j] = gain

            dp[i][j] = best
            back[i][j] = best_k

    # Select final boundary: either full coverage (j = n_segs) or best reachable.
    if require_full_coverage:
        j_end = n_segs
        if dp[n_paras][j_end] == NEG:
            j_end = max(range(n_paras, n_segs + 1), key=lambda j: dp[n_paras][j])
    else:
        j_end = max(range(n_paras, n_segs + 1), key=lambda j: dp[n_paras][j])

    if dp[n_paras][j_end] == NEG:
        return empty_output_rows(edited)

    # Backtrack selected spans from the best terminal state.
    spans: list[Span | None] = [None] * n_paras
    j = j_end
    for i in range(n_paras, 0, -1):
        k = back[i][j]
        if k < 0:
            spans[i - 1] = (None, None, 0.0)
            continue
        spans[i - 1] = (k, j - 1, local_score[i][j])
        j = k

    # Convert spans to output rows expected by callers.
    out: list[AlignmentRow] = []
    for idx, para_text in enumerate(edited):
        s_idx, e_idx, gain = spans[idx]
        if s_idx is None or e_idx is None or s_idx > e_idx:
            out.append(
                {
                    "start": None,
                    "end": None,
                    "text": para_text,
                    "match_score": 0.0,
                    "source_start_index": None,
                    "source_end_index": None,
                }
            )
            continue

        out.append(
            {
                "start": None,
                "end": None,
                "text": para_text,
                "match_score": round(float(gain), 6),
                "source_start_index": s_idx,
                "source_end_index": e_idx,
            }
        )

    return out
