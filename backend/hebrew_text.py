"""Pure helpers to build Hebrew search keys for the glossary.

- ``normalize_hebrew``: exact key (``hebrew_norm``). NFC, no cantillation
  marks (te'amim) or meteg, standardized geresh/gershayim, single spaces.
  Vowel points (niqqud) are kept.
- ``hebrew_consonants``: fallback key (``hebrew_cons``). Same as above with
  every niqqud mark removed.
"""

import re
import unicodedata

# Cantillation marks (te'amim): U+0591..U+05AF.
_CANTILLATION_RE = re.compile("[֑-֯]")
_METEG = "ֽ"
# Niqqud and other point marks: sheva..dagesh (U+05B0..U+05BC), meteg, rafe,
# shin/sin dots, upper/lower dots, qamats qatan. Maqaf (U+05BE), paseq
# (U+05C0), sof pasuq (U+05C3) and nun hafukha (U+05C6) are punctuation: kept.
_NIQQUD_RE = re.compile("[ְ-ׇּֽֿׁׂׅׄ]")
_HEBREW_LETTER_RE = re.compile("[א-ת]")
_WHITESPACE_RE = re.compile(r"\s+")

GERESH = "׳"  # ׳
GERSHAYIM = "״"  # ״
_SINGLE_QUOTES = "'‘’‛`´ʹʼ" + GERESH
_DOUBLE_QUOTES = '"“”„‟ʺ' + GERSHAYIM
_QUOTE_TABLE = str.maketrans(
    {**{c: GERESH for c in _SINGLE_QUOTES}, **{c: GERSHAYIM for c in _DOUBLE_QUOTES}}
)


# A Hebrew expression runs from its first Hebrew letter to its last Hebrew
# letter (with its trailing points), plus an optional geresh-like mark closing
# an abbreviation (e.g. וכו׳).
_HEBREW_SPAN_RE = re.compile(
    r"[א-ת](?:.*[א-ת])?"
    r"[֑-ׇֽֿׁׂׅׄ]*"
    r"['’׳]?",
    re.DOTALL,
)


# Doubt markers added by the correction LLM: <d alt="...">text</d>. The opening
# tag (with its attributes, quoted values may contain spaces or '>') and the
# closing tag are removed; the marked text itself is kept.
_DOUBT_OPEN_TAG_RE = re.compile(r"""<d\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.IGNORECASE)
_DOUBT_CLOSE_TAG_RE = re.compile(r"</d\s*>", re.IGNORECASE)


def strip_doubt_tags(text: str) -> str:
    """Remove ``<d ...>`` / ``</d>`` doubt tags, keeping the text between them."""
    value = _DOUBT_OPEN_TAG_RE.sub("", str(text or ""))
    return _DOUBT_CLOSE_TAG_RE.sub("", value)


def contains_hebrew_letter(text: str) -> bool:
    """True when the text contains at least one Hebrew letter (alef..tav)."""
    return bool(_HEBREW_LETTER_RE.search(text or ""))


def normalize_hebrew(text: str) -> str:
    """Exact search key: NFC, no te'amim/meteg, standard quotes, keeps niqqud."""
    value = unicodedata.normalize("NFC", str(text or ""))
    value = _CANTILLATION_RE.sub("", value).replace(_METEG, "")
    value = value.translate(_QUOTE_TABLE)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return unicodedata.normalize("NFC", value)


def hebrew_consonants(text: str) -> str:
    """Fallback search key: ``normalize_hebrew`` without any niqqud."""
    value = _NIQQUD_RE.sub("", normalize_hebrew(text))
    return unicodedata.normalize("NFC", value)


def _is_hebrew_token(token: str) -> bool:
    return contains_hebrew_letter(token)


def _merge_segment_pair(first: dict, second: dict) -> dict:
    merged = dict(first)
    merged["end"] = second["end"]
    merged["text"] = f"{first['text'].rstrip()} {second['text'].lstrip()}".strip()
    return merged


def merge_hebrew_segments(segments: list[dict]) -> list[dict]:
    """Merge consecutive segments joined by Hebrew words.

    Two consecutive segments are merged when the last word of the first and
    the first word of the second both contain Hebrew letters (punctuation
    attached to the words is ignored). Merging repeats, so a Hebrew passage
    spread over several segments ends up in a single segment spanning
    ``start`` of the first to ``end`` of the last. Doubt tags are ignored for
    the decision (an ``alt`` attribute does not count as a Hebrew word) but
    kept in the merged text.
    """
    merged: list[dict] = []
    for segment in segments:
        text = str(segment.get("text") or "")
        if merged:
            previous_words = strip_doubt_tags(merged[-1].get("text")).split()
            next_words = strip_doubt_tags(text).split()
            if (
                previous_words
                and next_words
                and _is_hebrew_token(previous_words[-1])
                and _is_hebrew_token(next_words[0])
            ):
                merged[-1] = _merge_segment_pair(merged[-1], {**segment, "text": text})
                continue
        merged.append(dict(segment))
    return merged


# Any HTML tag (doubt tags, source markers...): never part of a Hebrew term.
_HTML_TAG_RE = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""")
# Longest sub-expression looked up in the glossary (long quotations included).
MAX_LOOKUP_WORDS = 40


def _hebrew_runs(text: str) -> list[list[str]]:
    """Runs of consecutive Hebrew words, each word trimmed to its Hebrew span."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in _HTML_TAG_RE.sub(" ", str(text or "")).split():
        match = _HEBREW_SPAN_RE.search(token)
        if match:
            current.append(match.group(0))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def hebrew_lookup_keys(text: str, max_words: int = MAX_LOOKUP_WORDS) -> tuple[set[str], set[str]]:
    """Glossary keys (``hebrew_norm``, ``hebrew_cons``) of every Hebrew sub-expression.

    Every contiguous sequence of up to ``max_words`` words inside a Hebrew run
    is a candidate, so a run made of several glossary terms finds each of
    them. HTML tags are ignored. The client picks the actual matches
    (longest first); this only has to return a superset.
    """
    norms: set[str] = set()
    consonants: set[str] = set()
    for run in _hebrew_runs(text):
        for start in range(len(run)):
            for end in range(start + 1, min(len(run), start + max_words) + 1):
                expression = " ".join(run[start:end])
                norms.add(normalize_hebrew(expression))
                consonants.add(hebrew_consonants(expression))
    norms.discard("")
    consonants.discard("")
    return norms, consonants


def extract_hebrew_expressions(text: str) -> list[str]:
    """Hebrew words and expressions found in a text, in order of appearance.

    An expression is a maximal run of consecutive whitespace-separated words
    that contain Hebrew letters; a word without Hebrew letters ends the run.
    Leading/trailing punctuation is trimmed (a closing geresh of an
    abbreviation is kept). Duplicates (same ``normalize_hebrew`` key) are
    returned once. Doubt tags (``<d alt=...>…</d>``) are removed first: only
    the marked text is kept, never the tags or their ``alt`` attribute.
    """
    runs: list[list[str]] = []
    current: list[str] = []
    for token in strip_doubt_tags(text).split():
        if _is_hebrew_token(token):
            current.append(token)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)

    expressions: list[str] = []
    seen: set[str] = set()
    for run in runs:
        match = _HEBREW_SPAN_RE.search(" ".join(run))
        if not match:
            continue
        expression = _WHITESPACE_RE.sub(" ", match.group(0)).strip()
        key = normalize_hebrew(expression)
        if key and key not in seen:
            seen.add(key)
            expressions.append(expression)
    return expressions
