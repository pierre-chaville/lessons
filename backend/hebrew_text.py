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
    ``start`` of the first to ``end`` of the last.
    """
    merged: list[dict] = []
    for segment in segments:
        text = str(segment.get("text") or "")
        if merged:
            previous_words = str(merged[-1].get("text") or "").split()
            next_words = text.split()
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


def extract_hebrew_expressions(text: str) -> list[str]:
    """Hebrew words and expressions found in a text, in order of appearance.

    An expression is a maximal run of consecutive whitespace-separated words
    that contain Hebrew letters; a word without Hebrew letters ends the run.
    Leading/trailing punctuation is trimmed (a closing geresh of an
    abbreviation is kept). Duplicates (same ``normalize_hebrew`` key) are
    returned once.
    """
    runs: list[list[str]] = []
    current: list[str] = []
    for token in str(text or "").split():
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
