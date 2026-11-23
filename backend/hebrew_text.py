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
