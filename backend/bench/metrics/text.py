"""Text helpers shared by the correction metrics: normalization, tokenization, alignment."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from rapidfuzz.distance import Levenshtein

from bench.dataset import Segment, parse_transcript

_APOSTROPHES = str.maketrans({c: "'" for c in "’‘ʼ`´ʹ′"})
_HYPHENS = str.maketrans({c: "-" for c in "‐‑"})
_SPEAKER_TAG_RE = re.compile(r"^\[[^\]]*\]\s*")
# Doubt tags of the transcripts: `<d alt="..." i="...">chosen value</d>` (a quoted attribute may contain ">").
DOUBT_OPEN = r'<d\b(?:[^>"]|"[^"]*")*>'
DOUBT_CLOSE = r"</d\s*>"
_DOUBT_TAG_RE = re.compile(f"{DOUBT_OPEN}|{DOUBT_CLOSE}")


def strip_speaker_tag(text: str) -> str:
    return _SPEAKER_TAG_RE.sub("", text)


def strip_doubt_tags(text: str) -> str:
    """`du <d i="Shurim" alt="...">שִׁיעוּר</d>` -> `du שִׁיעוּר`: only the value chosen by the model is kept,
    so neither the tags nor their alternatives are compared."""
    return _DOUBT_TAG_RE.sub("", text)


def segment_text(text: str) -> str:
    """Text of a segment as compared by the correction metrics: doubt tags and speaker tag removed."""
    return strip_speaker_tag(strip_doubt_tags(text))


def segment_texts(text: str) -> tuple[list[str], Optional[list[Segment]]]:
    """Texts to compare: the segment texts of a `- [start - end] text` transcript (speaker tags
    such as `[audience]` and doubt tags removed), else the whole text (doubt tags removed).
    Returns (texts, segments or None)."""
    segments, _ = parse_transcript(text)
    if not segments:
        return [strip_doubt_tags(text)], None
    return [segment_text(s.text) for s in segments], segments


def tokenize(text: str, strict: bool = False, lowercase: bool = True) -> list[str]:
    """Words of a text.

    Default: lowercase, apostrophes unified, punctuation removed; apostrophes and hyphens inside
    words are kept (`l'a`, `ha-nahar`, `'hazal`), Hebrew letters keep their vowel points.
    lowercase=False: same, but case counts.
    strict=True: raw whitespace split (case and punctuation count).
    """
    text = unicodedata.normalize("NFC", text)
    if strict:
        return text.split()
    if lowercase:
        text = text.casefold()
    text = text.translate(_APOSTROPHES).translate(_HYPHENS)
    kept = "".join(
        c if c.isalnum() or c in "'-" or unicodedata.category(c).startswith("M") else " " for c in text
    )
    tokens = []
    for token in kept.split():
        token = token.strip("-").rstrip("'")
        if any(c.isalnum() for c in token):
            tokens.append(token)
    return tokens


def normalize(text: str, strict: bool = False) -> str:
    return " ".join(tokenize(text, strict))


def strip_accents(word: str) -> str:
    """Sinaï -> Sinai, מִשְׁכָּן -> משכן (combining marks removed)."""
    decomposed = unicodedata.normalize("NFD", word)
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if unicodedata.category(c) != "Mn"))


def norm_word(token: str) -> str:
    """Token of `tokenize` (lowercase, no punctuation) without accents, inner apostrophes and hyphens:
    ha-Nahar = HaNahar, Sinaï = Sinai."""
    return strip_accents(token).replace("'", "").replace("-", "")


def fold_word(token: str) -> str:
    """norm_word + `fold`: transliteration variants are equal (Parashah = parasha)."""
    return fold(norm_word(token))


WORD_LEVELS = {"norm": norm_word, "fold": fold_word}


def words_at_level(text: str, level: Optional[str] = None, strict: bool = False) -> list[str]:
    """Words of `text` for the WER variants: tokenize (level None), then norm_word or fold_word."""
    tokens = tokenize(text, strict)
    if level is None:
        return tokens
    transform = WORD_LEVELS[level]
    return [w for w in (transform(t) for t in tokens) if w]


def plain_text(text: str) -> str:
    """Text of a transcript (segments joined, timestamps and speaker tags removed) or of a markdown text."""
    return " ".join(segment_texts(text)[0])


def count_words(text: str) -> int:
    """Words of a transcript or a markdown text (markdown symbols and punctuation are not words)."""
    return len(tokenize(plain_text(text)))


def contains_words(haystack: list[str], needle: list[str]) -> bool:
    """True if the word sequence `needle` appears in `haystack` (tokens never contain spaces)."""
    return bool(needle) and f" {' '.join(needle)} " in f" {' '.join(haystack)} "


@dataclass
class Unit:
    """Aligned piece of text: a segment when the transcripts keep the same segments, else the whole text."""

    index: int
    start: Optional[int]  # seconds, None for the whole text
    texts: tuple[str, ...]  # one text per compared document


def same_segments(*segment_lists: Optional[list[Segment]]) -> bool:
    if any(s is None for s in segment_lists):
        return False
    first = [(s.start, s.end) for s in segment_lists[0]]
    return all([(s.start, s.end) for s in other] == first for other in segment_lists[1:])


def units(*documents: str, by_segment: bool = True) -> tuple[list[Unit], bool]:
    """Split documents into aligned units. Returns (units, segment_aligned)."""
    parsed = [segment_texts(d) for d in documents]
    if by_segment and same_segments(*(segments for _, segments in parsed)):
        segments = parsed[0][1]
        return [
            Unit(i, segments[i].start, tuple(texts[i] for texts, _ in parsed)) for i in range(len(segments))
        ], True
    return [Unit(0, None, tuple(" ".join(texts) for texts, _ in parsed))], False


@dataclass
class ErrorCounts:
    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0
    ref_length: int = 0
    hyp_length: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    def __iadd__(self, other: "ErrorCounts") -> "ErrorCounts":
        self.substitutions += other.substitutions
        self.deletions += other.deletions
        self.insertions += other.insertions
        self.ref_length += other.ref_length
        self.hyp_length += other.hyp_length
        return self

    def rate(self) -> Optional[float]:
        """errors / reference length; None when the reference is empty."""
        return self.errors / self.ref_length if self.ref_length else None


def error_counts(ref, hyp) -> ErrorCounts:
    """Minimal edit operations from ref to hyp (sequences of words or a string of characters)."""
    counts = ErrorCounts(ref_length=len(ref), hyp_length=len(hyp))
    for op in Levenshtein.editops(ref, hyp):
        if op.tag == "replace":
            counts.substitutions += 1
        elif op.tag == "delete":
            counts.deletions += 1
        else:
            counts.insertions += 1
    return counts


@dataclass(frozen=True)
class Edit:
    """Replacement of source[start:end] by `target` (start == end for an insertion)."""

    start: int
    end: int
    target: tuple[str, ...]


def edits(source: list[str], target: list[str]) -> list[Edit]:
    """Word diff source -> target: adjacent non-equal operations are merged into one edit."""
    result: list[Edit] = []
    current: Optional[list] = None  # [start, end, dest_start, dest_end]
    for op in Levenshtein.opcodes(source, target):
        if op.tag == "equal":
            if current:
                result.append(Edit(current[0], current[1], tuple(target[current[2] : current[3]])))
                current = None
        elif current is None:
            current = [op.src_start, op.src_end, op.dest_start, op.dest_end]
        else:
            current[1], current[3] = op.src_end, op.dest_end
    if current:
        result.append(Edit(current[0], current[1], tuple(target[current[2] : current[3]])))
    return result


def unchanged_positions(source: list[str], target: list[str]) -> set[int]:
    """Indices of the source words kept as is in target."""
    kept: set[int] = set()
    for op in Levenshtein.opcodes(source, target):
        if op.tag == "equal":
            kept.update(range(op.src_start, op.src_end))
    return kept


# Scholarly transliteration letters without a plain equivalent after accent removal (ḥ, ṭ, ḳ... lose
# their dot below with the accents): š = sh, ṣ = ts; ʿ ʾ (ayin, alef) and quote-like marks are removed.
_SCHOLARLY = str.maketrans({"š": "sh", "ṣ": "ts", "ʿ": "", "ʾ": "", "ʻ": "", "ʼ": "", "‘": "", "’": "", "´": ""})


def fold(word: str) -> str:
    """ replaces transliterated words by their original form """
    w = unicodedata.normalize("NFD", unicodedata.normalize("NFC", word).lower().translate(_SCHOLARLY))
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")   # accents : Sinaï -> sinai, Pessaḥ -> pessah
    w = re.sub(r"['`\-]", "", w)                                      # 'Omer, ha-Lou'hoth
    for a, b in [("tz", "ts"), ("th", "t"), ("sh", "ch"), ("q", "k"), ("ou", "u"),
                 ("ei", "e"), ("ph", "f"), ("ck", "k"), 
                 ("ss", "s"), ("nn", "n"), ("yy", "y"), ("tt", "t"), ("rr", "r"), ("ll", "l"), ("mm", "m"), ("pp", "p"), ("kk", "k"),
                 ("bb", "b"), ("dd", "d"), ("gg", "g"), ("cc", "c"), ("zz", "z")]:
        w = w.replace(a, b)
    for a, b in [("1", "un"), ("2", "deux"), ("3", "trois"), ("4", "quatre"), ("5", "cinq"), ("6", "six"), ("7", "sept"), ("8", "huit"), ("9", "neuf"), ("0", "zero"),
                 ("10", "dix"), ("20", "vingt"), ("30", "trente"), ("40", "quarante"), ("50", "cinquante"), 
                 ("100", "cent"), ("1000", "mille")]:
        if w == a:
            w = b

    w = re.sub(r"(.)\1+", r"\1", w)                                   # Assereth -> asereth
    w = re.sub(r"(?<=[aeiouy])h$", "", w)                             # Moshéh, Marah -> moshe, mara
    return w