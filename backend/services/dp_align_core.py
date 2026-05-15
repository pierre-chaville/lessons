import math
import re
import unicodedata
from collections import Counter
from typing import TypedDict

import numpy as np

try:
    from numba import njit

    NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    njit = None
    NUMBA_AVAILABLE = False

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


def _build_vocab_index(idf: dict[str, float]) -> tuple[dict[str, int], np.ndarray]:
    terms = list(idf.keys())
    index = {term: i for i, term in enumerate(terms)}
    idf_arr = np.array([idf[term] for term in terms], dtype=np.float64)
    return index, idf_arr


def _build_segment_csr(
    transcript: list[str], term_index: dict[str, int]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    indptr: list[int] = [0]
    indices: list[int] = []
    counts: list[float] = []
    seg_lens: list[int] = []
    for text in transcript:
        seg_count = Counter(tokenize(text))
        seg_lens.append(sum(seg_count.values()))
        for term, cnt in seg_count.items():
            idx = term_index.get(term)
            if idx is None:
                continue
            indices.append(idx)
            counts.append(float(cnt))
        indptr.append(len(indices))
    return (
        np.array(indptr, dtype=np.int32),
        np.array(indices, dtype=np.int32),
        np.array(counts, dtype=np.float64),
        np.array(seg_lens, dtype=np.int32),
    )


def _build_para_coefficients(
    edited: list[str],
    term_index: dict[str, int],
    idf_arr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_paras = len(edited)
    vocab_size = int(idf_arr.shape[0])
    para_coeff = np.zeros((n_paras, vocab_size), dtype=np.float64)
    para_norms = np.zeros(n_paras, dtype=np.float64)
    para_lens = np.zeros(n_paras, dtype=np.int32)
    idf_sq = idf_arr * idf_arr

    for i, para_text in enumerate(edited):
        counts = Counter(tokenize(para_text))
        para_lens[i] = max(1, sum(counts.values()))
        norm_sq = 0.0
        for term, cnt in counts.items():
            idx = term_index.get(term)
            if idx is None:
                continue
            para_coeff[i, idx] = float(cnt) * idf_sq[idx]
            # Paragraph norm is based on vec weight: tf * idf
            norm_sq += float(cnt * cnt) * idf_sq[idx]
        para_norms[i] = math.sqrt(norm_sq)

    return para_coeff, para_norms, para_lens


if NUMBA_AVAILABLE:

    @njit(cache=True)
    def _align_dp_numba_core(
        seg_indptr: np.ndarray,
        seg_indices: np.ndarray,
        seg_counts: np.ndarray,
        seg_lens: np.ndarray,
        para_coeff: np.ndarray,
        para_norms: np.ndarray,
        para_lens: np.ndarray,
        idf_sq: np.ndarray,
        max_window_segments: int,
        length_penalty_strength: float,
        require_full_coverage: bool,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n_paras = para_coeff.shape[0]
        n_segs = seg_lens.shape[0]
        vocab_size = para_coeff.shape[1]

        dp = np.full((n_paras + 1, n_segs + 1), NEG, dtype=np.float64)
        back = np.full((n_paras + 1, n_segs + 1), -1, dtype=np.int32)
        local = np.full((n_paras + 1, n_segs + 1), NEG, dtype=np.float64)
        dp[0, 0] = 0.0

        for i in range(1, n_paras + 1):
            para_norm = para_norms[i - 1]
            para_len = para_lens[i - 1]

            j_lo = i
            j_hi = n_segs - (n_paras - i)
            if j_lo > j_hi:
                continue

            for j in range(j_lo, j_hi + 1):
                window_counts = np.zeros(vocab_size, dtype=np.float64)
                dot = 0.0
                norm_sq = 0.0
                window_len = 0
                best = NEG
                best_k = -1
                best_gain = NEG

                k_lo = i - 1
                if j - max_window_segments > k_lo:
                    k_lo = j - max_window_segments

                for k in range(j - 1, k_lo - 1, -1):
                    window_len += seg_lens[k]
                    start = seg_indptr[k]
                    end = seg_indptr[k + 1]

                    for p in range(start, end):
                        t = seg_indices[p]
                        cnt = seg_counts[p]
                        old = window_counts[t]
                        new = old + cnt
                        window_counts[t] = new
                        norm_sq += idf_sq[t] * (new * new - old * old)
                        dot += para_coeff[i - 1, t] * cnt

                    prev = dp[i - 1, k]
                    if prev == NEG or norm_sq == 0.0 or para_norm == 0.0:
                        continue

                    sim = dot / (para_norm * math.sqrt(norm_sq))
                    ratio = window_len / para_len
                    if ratio < 1e-9:
                        ratio = 1e-9
                    length_prior = math.exp(
                        -length_penalty_strength * abs(math.log(ratio))
                    )

                    gain = sim * length_prior
                    score = prev + gain
                    if score > best:
                        best = score
                        best_k = k
                        best_gain = gain

                dp[i, j] = best
                back[i, j] = best_k
                local[i, j] = best_gain

        # Select final boundary.
        if require_full_coverage:
            j_end = n_segs
            if dp[n_paras, j_end] == NEG:
                best_j = n_paras
                best_val = NEG
                for j in range(n_paras, n_segs + 1):
                    val = dp[n_paras, j]
                    if val > best_val:
                        best_val = val
                        best_j = j
                j_end = best_j
        else:
            best_j = n_paras
            best_val = NEG
            for j in range(n_paras, n_segs + 1):
                val = dp[n_paras, j]
                if val > best_val:
                    best_val = val
                    best_j = j
            j_end = best_j

        starts = np.full(n_paras, -1, dtype=np.int32)
        ends = np.full(n_paras, -1, dtype=np.int32)
        gains = np.zeros(n_paras, dtype=np.float64)
        if dp[n_paras, j_end] == NEG:
            return starts, ends, gains

        j = j_end
        for i in range(n_paras, 0, -1):
            k = back[i, j]
            if k >= 0:
                starts[i - 1] = k
                ends[i - 1] = j - 1
                gains[i - 1] = local[i, j]
                j = k
        return starts, ends, gains


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


def _align_dp_texts_python(
    transcript: list[str],
    edited: list[str],
    max_window_segments: int = 40,
    length_penalty_strength: float = 0.6,
    require_full_coverage: bool = True,
) -> list[AlignmentRow]:
    """Pure-python fallback implementation (same behavior as pre-numba version)."""
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

    dp: list[list[float]] = [[NEG] * (n_segs + 1) for _ in range(n_paras + 1)]
    back: list[list[int]] = [[-1] * (n_segs + 1) for _ in range(n_paras + 1)]
    local_score: list[list[float]] = [[NEG] * (n_segs + 1) for _ in range(n_paras + 1)]
    dp[0][0] = 0.0

    for i in range(1, n_paras + 1):
        para_vec = para_vecs[i - 1]
        para_norm = para_norms[i - 1]
        para_len = para_lens[i - 1]

        j_lo = i
        j_hi = n_segs - (n_paras - i)
        if j_lo > j_hi:
            continue

        for j in range(j_lo, j_hi + 1):
            window_counts: Counter[str] = Counter()
            dot, norm_sq, window_len = 0.0, 0.0, 0
            best, best_k = NEG, -1
            k_lo = max(i - 1, j - max_window_segments)

            for k in range(j - 1, k_lo - 1, -1):
                window_len += seg_lens[k]
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

    if require_full_coverage:
        j_end = n_segs
        if dp[n_paras][j_end] == NEG:
            j_end = max(range(n_paras, n_segs + 1), key=lambda j: dp[n_paras][j])
    else:
        j_end = max(range(n_paras, n_segs + 1), key=lambda j: dp[n_paras][j])

    if dp[n_paras][j_end] == NEG:
        return empty_output_rows(edited)

    spans: list[Span | None] = [None] * n_paras
    j = j_end
    for i in range(n_paras, 0, -1):
        k = back[i][j]
        if k < 0:
            spans[i - 1] = (None, None, 0.0)
            continue
        spans[i - 1] = (k, j - 1, local_score[i][j])
        j = k

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
    if not NUMBA_AVAILABLE:
        return _align_dp_texts_python(
            transcript=transcript,
            edited=edited,
            max_window_segments=max_window_segments,
            length_penalty_strength=length_penalty_strength,
            require_full_coverage=require_full_coverage,
        )

    idf: dict[str, float] = build_idf(transcript, edited)
    term_index, idf_arr = _build_vocab_index(idf)
    seg_indptr, seg_indices, seg_counts, seg_lens = _build_segment_csr(
        transcript, term_index
    )
    para_coeff, para_norms, para_lens = _build_para_coefficients(
        edited, term_index, idf_arr
    )
    idf_sq = idf_arr * idf_arr

    try:
        starts, ends, gains = _align_dp_numba_core(
            seg_indptr=seg_indptr,
            seg_indices=seg_indices,
            seg_counts=seg_counts,
            seg_lens=seg_lens,
            para_coeff=para_coeff,
            para_norms=para_norms,
            para_lens=para_lens,
            idf_sq=idf_sq,
            max_window_segments=max_window_segments,
            length_penalty_strength=length_penalty_strength,
            require_full_coverage=require_full_coverage,
        )
    except Exception:
        # If numba compilation/cache fails at runtime, keep behavior correct.
        return _align_dp_texts_python(
            transcript=transcript,
            edited=edited,
            max_window_segments=max_window_segments,
            length_penalty_strength=length_penalty_strength,
            require_full_coverage=require_full_coverage,
        )

    if np.all(starts < 0):
        return empty_output_rows(edited)

    # Convert spans to output rows expected by callers.
    out: list[AlignmentRow] = []
    for idx, para_text in enumerate(edited):
        s_idx = int(starts[idx])
        e_idx = int(ends[idx])
        gain = float(gains[idx])
        if s_idx < 0 or e_idx < 0 or s_idx > e_idx:
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
                "source_start_index": int(s_idx),
                "source_end_index": int(e_idx),
            }
        )

    return out
