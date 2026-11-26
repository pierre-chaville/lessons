"""Hebrew words of the correction transcripts (the correction prompt writes them in Hebrew script).

Shared by the metrics of the three levels of comparison with corrected.md, and by the segment view
of the review app (its colors and counters come from the same `compare_unit`):

- A. Hebrew identification (hebrew_identification, hebrew_script_rate, vocalized_rate): each Hebrew
  word of the gold, aligned segment by segment, is classified against its counterpart in the
  output (categories below).
- B. French text (wer_french): every Hebrew passage replaced by a `⟨HE⟩` token; the differences
  are `french_error` (up to 3 words) or `drift` (insertion / replacement of more than 3 words).
- C. Final rendering (wer_rendered): both texts rendered as the app displays them, through the
  glossary (`render`).

Comparison keys of a Hebrew word:
- `he_key`: without points nor cantillation, standard geresh / gershayim. מִצְוֹת and מִצְווֹת differ
  (defective / plene spelling).
- `he_skeleton`: `he_key` without the inner vowel letters ו / י. מִצְוֹת and מִצְווֹת both give מצת.
Two words are the same word when they have the same `he_key`, or the same entry of the app
glossary (Hebrew-keyed, looked up as the app does), or - only when they are not both in the
glossary - the same skeleton.

A Latin word standing for a gold Hebrew word is compared through the glossary transliterations
(translit and aliases, words folded with text.fold), else phonetically (`latin_phonetic` /
`hebrew_phonetic`: consonant classes, vowels and gutturals ignored: Pessaḥ = פֶּסַח).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator, Optional

from rapidfuzz.distance import Levenshtein

from bench.dataset import parse_transcript
from bench.metrics.text import (_APOSTROPHES, _HYPHENS, _SCHOLARLY, _SPEAKER_TAG_RE, DOUBT_CLOSE, DOUBT_OPEN,
                                ErrorCounts, fold, tokenize, units)

HE_TOKEN = "⟨HE⟩"

_LETTERS = "א-ת"
# Points and cantillation marks of a word. Maqaf (U+05BE), paseq (U+05C0), sof pasuq (U+05C3) and
# nun hafukha (U+05C6) are punctuation: they separate words.
_MARK_CHARS = "֑-ׇֽֿׁׂׅׄ"
MARKS_RE = re.compile(f"[{_MARK_CHARS}]")
_VOWELS_RE = re.compile("[ְ-ׇֻ]")  # niqqud vowels: sheva .. qubuts, qamats qatan
_LETTER_RE = re.compile(f"[{_LETTERS}]")
# A Hebrew word: letters with their marks, inner quotes of an abbreviation (חֲזַ״ל, רַשִׁ"י) and an
# optional closing geresh (ה׳, ה').
_WORD_RE = re.compile(f"[{_LETTERS}][{_MARK_CHARS}]*(?:['\"׳״’]*[{_LETTERS}][{_MARK_CHARS}]*)*"
                      "['׳’]?")
_CHUNK_RE = re.compile("[^\\s־]+")  # whitespace and maqaf separate words
_DOUBT_RE = re.compile(f"({DOUBT_OPEN})|{DOUBT_CLOSE}")
_ATTRIBUTE_RE = re.compile(r'([\w-]+)="([^"]*)"')
_DAGESH, _HOLAM, _HOLAM_HASER, _SIN_DOT = "ּ", "ֹ", "ֺ", "ׂ"
_FINAL_LETTERS = str.maketrans("ךםןףץ", "כמנפצ")

PREFIX_LETTERS = "והבכלמש"  # ve-, ha-, be-, ke-, le-, mi-, she-
MAX_PREFIX = 3  # וּבְהַ...
MIN_STEM = 2  # letters left once the prefix is removed
SUFFIXES = ("ימ", "ות", "ינ", "ה", "ת", "י")  # plural, feminine, construct endings (final letters made regular)
MIN_FORM_STEM = 3  # letters left once a suffix is removed
MIN_PHONETIC = 2  # consonant classes needed to accept a Latin word phonetically
MAX_TERM_WORDS = 40  # longest glossary expression looked up (as the app)
LARGE_EDIT_WORDS = 3  # level B: an insertion / replacement of more words is a drift

# Level A categories, from the best to the worst counterpart of a gold word.
CATEGORIES = ("exact", "spelling_variant", "prefix_variant", "latin_correct", "unvocalized", "form_variant",
              "latin_uncorrected", "wrong_word", "missing")
IDENTIFIED = frozenset({"exact", "spelling_variant", "prefix_variant", "latin_correct"})
_RANK = {c: i for i, c in enumerate(CATEGORIES)}

# Severity of each difference category (review app colors), from the most to the least serious.
SEVERITIES = {
    "error": ("wrong_word", "latin_uncorrected", "missing", "french_error"),  # semantic error
    "drift": ("drift",),  # content drift: rewriting, addition
    "form": ("latin_correct", "form_variant", "unvocalized"),  # instruction or word form not respected
    "variant": ("spelling_variant", "prefix_variant", "french_variant"),  # harmless variant
    "cosmetic": ("minor", "exact_niqqud"),  # cosmetic difference
}
SEVERITY = {category: severity for severity, categories in SEVERITIES.items() for category in categories}
LABELS = {
    "wrong_word": "wrong word", "latin_uncorrected": "left uncorrected (Latin)", "missing": "missing",
    "french_error": "French error", "drift": "content drift", "latin_correct": "right word, Latin script",
    "form_variant": "word form (singular / plural...)", "unvocalized": "without vowel points",
    "spelling_variant": "spelling variant", "prefix_variant": "prefix variant", "french_variant": "one-letter difference (French)", "minor": "minor",
    "exact_niqqud": "vowel points differ",
}

# Numbers written in digits or in words are the same French word (the gold mixes both).
NUMBER_WORDS = {"0": "zéro", "1": "un", "2": "deux", "3": "trois", "4": "quatre", "5": "cinq", "6": "six",
                "7": "sept", "8": "huit", "9": "neuf", "10": "dix", "20": "vingt", "100": "cent", "1000": "mille"}


# --------------------------------------------------------------------------- #
# Words and keys
# --------------------------------------------------------------------------- #


def is_hebrew(text: str) -> bool:
    return bool(_LETTER_RE.search(text or ""))


def has_vowels(word: str) -> bool:
    return bool(_VOWELS_RE.search(word))


def is_abbreviation(word: str) -> bool:
    """ה׳, חז״ל...: written without vowel points."""
    key = he_key(word)
    return "׳" in key or "״" in key


def needs_vowels(word: str) -> bool:
    return not is_abbreviation(word)


def strip_points(text: str) -> str:
    return MARKS_RE.sub("", unicodedata.normalize("NFC", text))


def he_key(word: str) -> str:
    """Word without points nor cantillation, geresh / gershayim standardized."""
    w = strip_points(word)
    return w.replace('"', "״").replace("''", "״").replace("’", "׳").replace("'", "׳")


def he_skeleton(word: str) -> str:
    """he_key without the inner vowel letters (ו, י): defective and plene spellings are equal."""
    w = he_key(word)
    return w[0] + re.sub("[וי]", "", w[1:]) if w else w


@dataclass(frozen=True)
class Token:
    text: str  # Hebrew word as written (points kept), or French word as text.tokenize (case kept)
    hebrew: bool
    start: int = -1  # position in clean_text() of the segment (-1: rendered word)
    end: int = -1


@dataclass(frozen=True)
class Doubt:
    """`<d ...>value</d>` span of a text, in clean_text() positions."""

    start: int
    end: int
    attributes: dict = field(hash=False)


def doubts(text: str) -> tuple[str, list[Doubt]]:
    """(clean text, doubt spans): the text in NFC with the doubt tags removed (their value kept)."""
    text = unicodedata.normalize("NFC", text or "")
    clean: list[str] = []
    length = 0
    spans: list[Doubt] = []
    opened: Optional[tuple[int, dict]] = None
    position = 0
    for match in _DOUBT_RE.finditer(text):
        piece = text[position:match.start()]
        clean.append(piece)
        length += len(piece)
        position = match.end()
        if match.group(1):  # opening tag
            opened = (length, dict(_ATTRIBUTE_RE.findall(match.group(1))))
        elif opened is not None:
            spans.append(Doubt(opened[0], length, opened[1]))
            opened = None
    clean.append(text[position:])
    return "".join(clean), spans


def clean_text(text: str) -> str:
    """Text whose positions the tokens refer to: NFC, doubt tags removed."""
    return doubts(text)[0]


def _french_tokens(text: str, base: int) -> Iterator[Token]:
    """The words of text.tokenize (case kept), with their positions."""
    unified = text.translate(_APOSTROPHES).translate(_HYPHENS)  # same length
    kept = "".join(c if c.isalnum() or c in "'-" or unicodedata.category(c).startswith("M") else " " for c in unified)
    for match in re.finditer(r"\S+", kept):
        word = match.group()
        lead = len(word) - len(word.lstrip("-"))
        core = word.strip("-").rstrip("'")
        if any(c.isalnum() for c in core):
            start = match.start() + lead
            yield Token(core, False, base + start, base + start + len(core))


def tokens(text: str) -> list[Token]:
    """Words of a segment text, doubt tags and speaker tag removed. A word mixing scripts is split:
    `d'הַשֵּׁם` -> `d`, `הַשֵּׁם`. Punctuation is dropped, as in text.tokenize. Positions refer to
    clean_text(text)."""
    clean = clean_text(text)
    speaker = _SPEAKER_TAG_RE.match(clean)
    result: list[Token] = []
    for chunk in _CHUNK_RE.finditer(clean, speaker.end() if speaker else 0):
        base, word = chunk.start(), chunk.group()
        position = 0
        for match in _WORD_RE.finditer(word):
            result += _french_tokens(word[position:match.start()], base + position)
            result.append(Token(match.group(), True, base + match.start(), base + match.end()))
            position = match.end()
        result += _french_tokens(word[position:], base + position)
    return result


def _stems(word: str) -> Iterator[tuple[str, str]]:
    """(prefix, rest) of the he_key of a word, for every possible prefix (no prefix included)."""
    key = he_key(word)
    yield "", key
    for i in range(1, MAX_PREFIX + 1):
        if key[i - 1] not in PREFIX_LETTERS or len(key) - i < MIN_STEM:
            break
        yield key[:i], key[i:]


def prefix_variant(gold: str, output: str) -> bool:
    """Same word once a different prefix is removed (עֹמֶר / הָעוֹמֶר)."""
    return any(gp != op and he_skeleton(gs) == he_skeleton(os_)
               for gp, gs in _stems(gold) for op, os_ in _stems(output))


def _forms(word: str) -> Iterator[tuple[str, str]]:
    """(stem, suffix) of a word, prefixes removed, final letters made regular."""
    for _, rest in _stems(word):
        rest = rest.translate(_FINAL_LETTERS)
        yield rest, ""
        for suffix in SUFFIXES:
            if rest.endswith(suffix) and len(rest) - len(suffix) >= MIN_FORM_STEM:
                yield rest[:-len(suffix)], suffix


def form_variant(gold: str, output: str) -> bool:
    """Same stem with another ending (שִׁיעוּר / שִׁיעוּרִים, מִצְוָה / מִצְווֹת); endings that differ
    only by a vowel letter (ת / ות) are a spelling variant, not another form."""
    def ending(suffix: str) -> str:
        return re.sub("[וי]", "", suffix)

    return any(ending(gs) != ending(os_) and he_skeleton(g) == he_skeleton(o)
               for g, gs in _forms(gold) for o, os_ in _forms(output))


# --------------------------------------------------------------------------- #
# Phonetic comparison of a Latin word with a Hebrew word
# --------------------------------------------------------------------------- #

# Consonant classes; vowels, h / kh / ח / ה / א / ע / י are ignored (their transliterations vary).
_LATIN_DIGRAPHS = (("sch", "X"), ("sh", "X"), ("ch", "X"), ("kh", ""), ("tz", "C"), ("ts", "C"),
                   ("th", "T"), ("ph", "P"), ("ck", "K"), ("qu", "K"))
_LATIN_CLASSES = str.maketrans({"b": "B", "v": "B", "w": "B", "g": "G", "d": "D", "z": "Z", "t": "T", "k": "K",
                                "q": "K", "c": "K", "l": "L", "m": "M", "n": "N", "s": "S", "p": "P", "f": "P",
                                "r": "R", "x": "KS"})
_HEBREW_CLASSES = {"ב": "B", "ג": "G", "ד": "D", "ז": "Z", "ט": "T", "ל": "L", "מ": "M", "ם": "M", "נ": "N",
                   "ן": "N", "ס": "S", "פ": "P", "ף": "P", "צ": "C", "ץ": "C", "ק": "K", "ר": "R", "ת": "T"}


def latin_phonetic(word: str) -> str:
    w = unicodedata.normalize("NFD", unicodedata.normalize("NFC", word).lower().translate(_SCHOLARLY))
    w = re.sub("[^a-z]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))
    for a, b in _LATIN_DIGRAPHS:
        w = w.replace(a, b)
    w = re.sub("[a-z]", "", w.translate(_LATIN_CLASSES))
    return re.sub(r"(.)\1+", r"\1", w)


def hebrew_phonetic(word: str) -> str:
    vocalized = has_vowels(word)
    out = []
    for letter, marks in re.findall(f"([{_LETTERS}])([{_MARK_CHARS}]*)", unicodedata.normalize("NFC", word)):
        if letter == "ו":  # holam / shuruk: a vowel; else the consonant v
            vowel = (not vocalized or _HOLAM in marks or _HOLAM_HASER in marks
                     or (_DAGESH in marks and not _VOWELS_RE.search(marks)))
            out.append("" if vowel else "B")
        elif letter in "כך":  # kaf = k, khaf = guttural (ignored)
            out.append("K" if _DAGESH in marks else "")
        elif letter == "ש":
            out.append("S" if _SIN_DOT in marks else "X")
        else:
            out.append(_HEBREW_CLASSES.get(letter, ""))
    return re.sub(r"(.)\1+", r"\1", "".join(out))


def phonetic_match(hebrew_word: str, latin_word: str) -> bool:
    key = hebrew_phonetic(hebrew_word)
    return len(key) >= MIN_PHONETIC and latin_phonetic(latin_word) == key


# --------------------------------------------------------------------------- #
# Glossary (Hebrew-keyed glossary of the app DB)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GlossaryTerm:
    id: int
    hebrew: str
    translit: Optional[str]
    aliases: tuple[str, ...]
    type: str  # term, expression, quotation, proper_name, book...
    validated: bool
    norm: str  # hebrew_text.normalize_hebrew
    cons: str  # hebrew_text.hebrew_consonants


@lru_cache(maxsize=1)
def app_glossary() -> tuple[GlossaryTerm, ...]:
    """Entries of the app DB glossary, read once per process (scores depend on it: its size is
    stored in the details)."""
    from sqlmodel import Session, select

    from database import engine
    from models.glossary import GlossaryEntry

    with Session(engine) as session:
        return tuple(
            GlossaryTerm(e.id, e.hebrew, e.translit, tuple(e.aliases or ()), e.type, e.status == "validated",
                         e.hebrew_norm, e.hebrew_cons)
            for e in session.exec(select(GlossaryEntry)).all()
        )


class Glossary:
    """Lookup of a Hebrew word or expression as the app does: exact key, else consonants; on a
    key shared by several entries, a validated entry wins."""

    def __init__(self, terms: tuple[GlossaryTerm, ...]):
        self.size = len(terms)
        self.by_norm: dict[str, GlossaryTerm] = {}
        self.by_cons: dict[str, GlossaryTerm] = {}
        for term in terms:
            for index, key in ((self.by_norm, term.norm), (self.by_cons, term.cons)):
                existing = index.get(key)
                if existing is None or (not existing.validated and term.validated):
                    index[key] = term

    def lookup(self, expression: str) -> Optional[GlossaryTerm]:
        if not self.size:
            return None
        from hebrew_text import hebrew_consonants, normalize_hebrew

        return self.by_norm.get(normalize_hebrew(expression)) or self.by_cons.get(hebrew_consonants(expression))

    def latin_forms(self, term: GlossaryTerm) -> set[str]:
        """Folded transliterations of an entry (translit and aliases, words joined)."""
        return {"".join(fold(w) for w in tokenize(form)) for form in (term.translit, *term.aliases) if form}


@lru_cache(maxsize=1)
def _app_glossary_index() -> Glossary:
    return Glossary(app_glossary())


def load_glossary(use_glossary: bool = True) -> Glossary:
    return _app_glossary_index() if use_glossary else Glossary(())


def check_glossary_option(options: dict) -> list[str]:
    value = options.get("glossary", True)
    return [] if isinstance(value, bool) else [f"'glossary' must be true or false, got {value!r}"]


# --------------------------------------------------------------------------- #
# Level A: classification of the gold Hebrew words
# --------------------------------------------------------------------------- #

# Written forms of the same word: abbreviation and substitute spellings of the divine names.
EQUIVALENT_KEYS = {"ה׳": "השם", "אלקים": "אלהים", "אלוקים": "אלהים", "אלקינו": "אלהינו", "אלוקינו": "אלהינו"}


def same_word(gold: str, output: str, glossary: Glossary) -> bool:
    gold_key, output_key = he_key(gold), he_key(output)
    if gold_key == output_key or EQUIVALENT_KEYS.get(gold_key, gold_key) == EQUIVALENT_KEYS.get(output_key, output_key):
        return True
    gold_entry, output_entry = glossary.lookup(gold), glossary.lookup(output)
    if gold_entry and output_entry:
        return gold_entry.id == output_entry.id
    return he_skeleton(gold) == he_skeleton(output)


def latin_correct(gold: str, output: str, glossary: Glossary) -> bool:
    entry = glossary.lookup(gold)
    if entry and fold(output) in glossary.latin_forms(entry):
        return True
    return phonetic_match(gold, output)


def _french_word(word: str) -> bool:
    from bench.metrics.hebrew_term_accuracy import is_hebrew_term

    return not is_hebrew_term(word.lower(), min_length=1)


def classify(gold: Token, output: Token, glossary: Glossary, input_words: set[str]) -> Optional[str]:
    """Category of `output` as the counterpart of the gold Hebrew word, None if a Latin word is
    unrelated to it (a French word, or a new Latin word that is not its transliteration)."""
    if output.hebrew:
        if same_word(gold.text, output.text, glossary):
            if has_vowels(gold.text) and not has_vowels(output.text) and needs_vowels(output.text):
                return "unvocalized"
            return "exact" if he_key(gold.text) == he_key(output.text) else "spelling_variant"
        if prefix_variant(gold.text, output.text):
            return "prefix_variant"
        return "form_variant" if form_variant(gold.text, output.text) else "wrong_word"
    related = latin_correct(gold.text, output.text, glossary)
    if output.text.lower() in input_words:
        # Left as in the raw transcript: a transliteration (Amalek) or a garbled word (Amara), but
        # not a French word of the sentence unless it sounds like the gold word.
        return "latin_uncorrected" if related or not _french_word(output.text) else None
    return "latin_correct" if related else None


@dataclass
class Term:
    gold: str
    output: Optional[str]  # counterpart in the output, None when missing
    category: str
    start: Optional[int]  # start of the segment (s), None when the texts are compared as a whole
    gold_index: int = -1  # index of the gold word in UnitAnalysis.gold
    output_index: Optional[int] = None  # index of the counterpart in UnitAnalysis.output
    gap_at: int = 0  # missing: output index before which the word is missing

    @property
    def output_hebrew(self) -> bool:
        return self.output is not None and is_hebrew(self.output)

    @property
    def niqqud_differs(self) -> bool:
        """Exact word, other vowel points."""
        return self.category == "exact" and strip_cantillation(self.gold) != strip_cantillation(self.output or "")


def strip_cantillation(word: str) -> str:
    from hebrew_text import normalize_hebrew

    return normalize_hebrew(word)


@dataclass
class FrenchEdit:
    """Level B difference: gold words replaced by output words (⟨HE⟩ for a Hebrew passage)."""

    category: str  # french_error | drift
    gold: list[str]
    output: list[str]
    output_tokens: list[int]  # indices in UnitAnalysis.output of the output words
    gap_at: int  # output index before which the gold words are missing (deletion)

    @property
    def label(self) -> str:
        return f"{' '.join(self.gold) or '∅'} → {' '.join(self.output) or '∅'}"


@dataclass
class UnitAnalysis:
    start: Optional[int]
    gold: list[Token]
    output: list[Token]
    terms: list[Term]
    latin_counterparts: set[int]  # indices of the output Latin words standing for a gold Hebrew word
    gold_french: list[str] = field(default_factory=list)  # level B words (⟨HE⟩ tokens)
    output_french: list[str] = field(default_factory=list)
    edits: list[FrenchEdit] = field(default_factory=list)
    minor: list[tuple[int, str]] = field(default_factory=list)  # (output index, gold word): same French word written differently
    french_variants: list[tuple[int, str]] = field(default_factory=list)  # (output index, gold word): one letter differs
    french_counts: ErrorCounts = field(default_factory=ErrorCounts)  # level B word errors (variants excluded)


@dataclass
class Analysis:
    units: list[UnitAnalysis]
    glossary_entries: int
    segment_aligned: bool

    @property
    def terms(self) -> list[Term]:
        return [t for u in self.units for t in u.terms]

    @property
    def edits(self) -> list[FrenchEdit]:
        return [e for u in self.units for e in u.edits]


def _alignment_key(token: Token) -> str:
    return ("H" + he_skeleton(token.text)) if token.hebrew else ("L" + fold(token.text))


def blocks(gold_keys: list[str], output_keys: list[str]) -> Iterator[tuple[bool, int, int, int, int]]:
    """(equal, gold start, gold end, output start, output end): the alignment with adjacent
    non-equal operations merged (`à מָרָה` -> `Amara` is one block, whatever the edit path)."""
    pending: Optional[list[int]] = None
    for op in Levenshtein.opcodes(gold_keys, output_keys):
        if op.tag == "equal":
            if pending:
                yield False, *pending
                pending = None
            yield True, op.src_start, op.src_end, op.dest_start, op.dest_end
        elif pending is None:
            pending = [op.src_start, op.src_end, op.dest_start, op.dest_end]
        else:
            pending[1], pending[3] = op.src_end, op.dest_end
    if pending:
        yield False, *pending


def _hebrew_terms(start: Optional[int], gold: list[Token], output: list[Token], input_words: set[str],
                  glossary: Glossary) -> list[Term]:
    found: dict[int, tuple[Optional[int], str]] = {}  # gold index -> (output index, category)
    gap: dict[int, int] = {}  # gold index -> output index of its block
    for equal, g_start, g_end, o_start, o_end in blocks([_alignment_key(t) for t in gold],
                                                         [_alignment_key(t) for t in output]):
        hebrew = [k for k in range(g_start, g_end) if gold[k].hebrew]
        if equal:
            for k in hebrew:
                j = o_start + k - g_start
                found[k] = (j, classify(gold[k], output[j], glossary, input_words) or "wrong_word")
            continue
        gap.update((k, o_start) for k in hebrew)
        # Best counterparts first (category, then distance to the expected position).
        n_gold, n_out = g_end - g_start, o_end - o_start
        candidates = []
        for k in hebrew:
            expected = o_start + (k - g_start) * n_out / n_gold
            for j in range(o_start, o_end):
                category = classify(gold[k], output[j], glossary, input_words)
                if category is not None:
                    candidates.append((_RANK[category], abs(j - expected), k, j, category))
        used: set[int] = set()
        for _, _, k, j, category in sorted(candidates):
            if k not in found and j not in used:
                found[k] = (j, category)
                used.add(j)
        for k in hebrew:  # same number of words: the (non French) Latin word in place of the gold word
            j = o_start + k - g_start
            if k not in found and n_gold == n_out and j not in used and not _french_word(output[j].text):
                found[k] = (j, "wrong_word")
                used.add(j)
    terms = []
    for k, token in enumerate(gold):
        if token.hebrew:
            j, category = found.get(k, (None, "missing"))
            terms.append(Term(token.text, output[j].text if j is not None else None, category, start,
                              k, j, gap.get(k, j if j is not None else len(output))))
    return terms


def french_sequence(words: list[Token], hebrew_standins: set[int] = frozenset(),
                    case_sensitive: bool = False) -> tuple[list[str], list[list[int]]]:
    """Level B words and, for each, the indices of the tokens it stands for: each Hebrew passage
    (and each Latin word standing for a gold Hebrew word) is one ⟨HE⟩ token; numbers in digits are
    written in words."""
    keys: list[str] = []
    indices: list[list[int]] = []
    for index, token in enumerate(words):
        if token.hebrew or index in hebrew_standins:
            if keys and keys[-1] == HE_TOKEN:
                indices[-1].append(index)
            else:
                keys.append(HE_TOKEN)
                indices.append([index])
            continue
        word = NUMBER_WORDS.get(token.text, token.text)
        keys.append(word if case_sensitive else word.lower())
        indices.append([index])
    return keys, indices


def french_words(words: list[Token], hebrew_standins: set[int] = frozenset(), case_sensitive: bool = False) -> list[str]:
    return french_sequence(words, hebrew_standins, case_sensitive)[0]


def _one_letter(gold: str, output: str) -> bool:
    return gold != HE_TOKEN and output != HE_TOKEN and Levenshtein.distance(gold, output) == 1


def _french_differences(unit: UnitAnalysis, case_sensitive: bool, one_letter_variants: bool) -> None:
    """Level B: edits (french_error / drift), one-letter variants, minor differences and word
    error counts of a unit."""
    gold, gold_indices = french_sequence(unit.gold, case_sensitive=case_sensitive)
    out, out_indices = french_sequence(unit.output, unit.latin_counterparts, case_sensitive)
    unit.gold_french, unit.output_french = gold, out
    counts = unit.french_counts = ErrorCounts(ref_length=len(gold), hyp_length=len(out))

    def add_edit(g_start: int, g_end: int, o_start: int, o_end: int) -> None:
        n_gold, n_out = g_end - g_start, o_end - o_start
        counts.substitutions += min(n_gold, n_out)
        counts.deletions += max(n_gold - n_out, 0)
        counts.insertions += max(n_out - n_gold, 0)
        target = out[o_start:o_end]
        if not target and set(gold[g_start:g_end]) == {HE_TOKEN}:
            return  # a Hebrew passage missing from the output: reported by level A (missing)
        large = bool(target) and max(n_gold, n_out) > LARGE_EDIT_WORDS
        gap_at = out_indices[o_start][0] if o_start < len(out) else len(unit.output)
        unit.edits.append(FrenchEdit("drift" if large else "french_error", gold[g_start:g_end], target,
                                     [i for o in range(o_start, o_end) for i in out_indices[o]], gap_at))

    for equal, g_start, g_end, o_start, o_end in blocks(gold, out):
        if equal:
            for g, o in zip(range(g_start, g_end), range(o_start, o_end)):
                gold_token, out_token = unit.gold[gold_indices[g][0]], unit.output[out_indices[o][0]]
                if gold[g] != HE_TOKEN and gold_token.text != out_token.text:
                    unit.minor.append((out_indices[o][0], gold_token.text))
            continue
        if not one_letter_variants or g_end - g_start != o_end - o_start:
            add_edit(g_start, g_end, o_start, o_end)
            continue
        # Word for word: the words that differ by one letter are variants, the others edits.
        size = g_end - g_start
        run = None  # offset of the current run of real differences
        for offset in range(size + 1):
            variant = offset < size and _one_letter(gold[g_start + offset], out[o_start + offset])
            if offset < size and not variant:
                run = offset if run is None else run
                continue
            if run is not None:
                add_edit(g_start + run, g_start + offset, o_start + run, o_start + offset)
                run = None
            if variant:
                unit.french_variants.append((out_indices[o_start + offset][0],
                                             unit.gold[gold_indices[g_start + offset][0]].text))


def compare_unit(start: Optional[int], gold_text: str, output_text: str, input_text: str = "",
                 glossary: Optional[Glossary] = None, case_sensitive: bool = False,
                 one_letter_variants: bool = True) -> UnitAnalysis:
    """All the differences of one segment of the output with the gold: Hebrew words (level A) and
    French words (level B). The metrics and the review app colors come from this function."""
    glossary = glossary or Glossary(())
    gold, output = tokens(gold_text), tokens(output_text)
    input_words = {t.text.lower() for t in tokens(input_text) if not t.hebrew}
    terms = _hebrew_terms(start, gold, output, input_words, glossary)
    latin = {t.output_index for t in terms if t.output_index is not None and not output[t.output_index].hebrew}
    unit = UnitAnalysis(start, gold, output, terms, latin)
    _french_differences(unit, case_sensitive, one_letter_variants)
    return unit


def _input_texts(input_text: str) -> tuple[dict[int, str], str]:
    segments, _ = parse_transcript(input_text)
    return {s.start: s.text for s in segments}, " ".join(s.text for s in segments) or input_text


@lru_cache(maxsize=32)
def analyze(output: str, reference: str, input_text: str = "", use_glossary: bool = True,
            case_sensitive: bool = False, one_letter_variants: bool = True) -> Analysis:
    """compare_unit on each segment when the output keeps the segments of the reference, else on
    the whole texts. `input_text` (raw transcript) tells the Latin words left unchanged by the model."""
    glossary = load_glossary(use_glossary)
    segment_units, aligned = units(reference, output)
    by_start, whole_input = _input_texts(input_text or "")
    result = []
    for unit in segment_units:
        unit_input = by_start.get(unit.start, "") if aligned else whole_input
        result.append(compare_unit(unit.start, unit.texts[0], unit.texts[1], unit_input, glossary, case_sensitive,
                                   one_letter_variants))
    return Analysis(result, glossary.size, aligned)


def category_counts(unit: UnitAnalysis) -> dict[str, int]:
    """Number of differences per category (exact words with other vowel points: exact_niqqud)."""
    counts: dict[str, int] = {}
    for term in unit.terms:
        category = "exact_niqqud" if term.niqqud_differs else term.category
        if category != "exact":
            counts[category] = counts.get(category, 0) + 1
    for edit in unit.edits:
        counts[edit.category] = counts.get(edit.category, 0) + 1
    if unit.minor:
        counts["minor"] = counts.get("minor", 0) + len(unit.minor)
    if unit.french_variants:
        counts["french_variant"] = counts.get("french_variant", 0) + len(unit.french_variants)
    return counts


# --------------------------------------------------------------------------- #
# Level C: rendering through the glossary
# --------------------------------------------------------------------------- #

PRIMARY_FORMS = ("translit", "vocalized", "unvocalized")  # the app display settings (primary form)


def _render_entry(term: GlossaryTerm, primary: str, quotations_in_hebrew: bool) -> list[Token]:
    quotation_in_hebrew = term.type == "quotation" and quotations_in_hebrew
    if primary == "translit" and term.translit and not quotation_in_hebrew:
        return [Token(w, False) for w in tokenize(term.translit, lowercase=False)]
    return [Token(t.text, t.hebrew) for t in tokens(strip_points(term.hebrew) if primary == "unvocalized" else term.hebrew)]


def render(words: list[Token], glossary: Glossary, primary: str = "translit",
           quotations_in_hebrew: bool = True) -> tuple[list[Token], int]:
    """Words as the app displays them (frontend utils/hebrewText.ts, renderHebrewTerms): in each run
    of Hebrew words, the longest glossary expression first, rendered in the primary form (a
    transliteration falls back to Hebrew while the entry has none); other Hebrew words stay as
    written. Supplementary forms in parentheses are not rendered. Returns (words, glossary matches)."""
    result: list[Token] = []
    matches = 0
    i = 0
    while i < len(words):
        if not words[i].hebrew:
            result.append(words[i])
            i += 1
            continue
        end = i
        while end < len(words) and words[end].hebrew and end - i < MAX_TERM_WORDS:
            end += 1
        for j in range(end, i, -1):
            term = glossary.lookup(" ".join(t.text for t in words[i:j]))
            if term:
                result += _render_entry(term, primary, quotations_in_hebrew)
                matches += 1
                i = j
                break
        else:
            text = words[i].text
            result.append(Token(strip_points(text) if primary == "unvocalized" else text, True))
            i += 1
    return result, matches


def rendered_key(token: Token) -> str:
    """Comparison key of a rendered word: folded Latin word, Hebrew word without points."""
    return ("H" + he_key(token.text)) if token.hebrew else ("L" + fold(token.text))


def cross_script_matches(source: list[Token], target: list[Token]) -> int:
    """Pairs (Hebrew word, Latin word) that are the same word phonetically (Pessaḥ = פֶּסַח)."""
    used: set[int] = set()
    count = 0
    for a in source:
        for j, b in enumerate(target):
            if j in used or a.hebrew == b.hebrew:
                continue
            hebrew, latin = (a, b) if a.hebrew else (b, a)
            if phonetic_match(hebrew.text, latin.text):
                used.add(j)
                count += 1
                break
    return count
