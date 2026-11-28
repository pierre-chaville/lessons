"""hebrew_expression_format: share of the Hebrew expressions of the output introduced in full form.

Rule 2 of the edition prompt: a Hebrew expression of several words is written, at least once
(normally at its first occurrence), as Hebrew + transliteration + translation:

    וְאָהַבְתָּ לְרֵעֲךָ כָּמוֹךָ (*Ve'ahavta lere'akha kamokha*, "tu aimeras ton prochain comme toi-même")

Detection, on the output only:
- full / annotated forms: Hebrew script followed by `(*transliteration*, translation)`; the
  translation may be quoted (« », " ", “ ”) or not, after `,` `:` `;` or a spaced dash; a quoted
  translation just after the parenthesis (`(*Lo tov…*), « Il n'est pas bien… »`) is accepted too,
  unless `strict: true` (counted in `translation_after`); without translation the occurrence is
  `hebrew + transliteration` only;
- transliterated expressions: runs of at least `min_words` (default 2) consecutive words not in the
  French dictionary (pyspellchecker), at least one of them really not French (`ha-Miqdash` counts,
  `ha` alone does not). An italic span counts as one expression when most of its words are not
  French. A non-italic run whose words are all capitalized (likely a name: `Rav Grosstein`) only
  counts as an occurrence of an expression found elsewhere; patronymics (`Yehoshoua ben Levi`) and
  the `ignore` expressions of the options are skipped;
- Hebrew-script expressions of at least `min_words` words without transliteration.

Occurrences are grouped by transliteration (case, accents, apostrophes and hyphens ignored), or
by Hebrew text (vowel points ignored). An expression complies when one of its occurrences is in
full form, or is part of a full form (a word group of a quoted verse given in full).

Value = compliant expressions / expressions; None without any expression. Details: the
expressions in full form at their first occurrence (`first_occurrence_rate`), the problems of
the others (`no translation`, `no Hebrew`, `no transliteration`) and `items`: every expression
with its occurrences (offsets in the output, for the review app).
Option `require_first: true`: an expression only complies when its first occurrence is in full form.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from bench.metrics import MetricResult

HIGHER_IS_BETTER = True
REPORT_DETAILS = {"expressions": None, "first_occurrence_rate": True, "no_translation_rate": False,
                  "no_hebrew_rate": False, "no_transliteration_rate": False}
PERCENT = True
PERCENT_DETAILS = {"first_occurrence_rate", "no_translation_rate", "no_hebrew_rate", "no_transliteration_rate"}
NEEDS_REFERENCE = False

DEFAULT_MIN_WORDS = 2
ITEM_LIMIT = 150
SPAN_LIMIT = 30

_LETTERS = "\u05d0-\u05ea\ufb1d-\ufb4f"
_MARKS = "\u0591-\u05c7"
_HEB_WORD = rf"[{_LETTERS}][{_LETTERS}{_MARKS}\"'\u05f3\u05f4]*"
# Hebrew span: Hebrew words, possibly separated by punctuation inside a quoted verse.
_HEB_SPAN = rf"{_HEB_WORD}(?:[\s\u05be,.;:«»“”-]+{_HEB_WORD})*"
_FULL_RE = re.compile(
    rf"(?P<heb>{_HEB_SPAN})[\s»\"”“'’.,;:!?]*"
    r"\(\s*(?:\*(?P<italic>[^*\n]+)\*|(?P<plain>[^*,;:()\n]+?))"
    r"\s*(?:(?:[,;:]|\s[–—-]\s)\s*(?P<translation>[^()\n]*?))?\s*\)"
    rf"(?:[ \t]*[,:]?[ \t]*[«\"“](?P<after>[^»\"”\n{_LETTERS}{_MARKS}]+)[»\"”])?"
)
_HEB_SPAN_RE = re.compile(_HEB_SPAN)
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?!\*)(?P<text>[^*\n]+?)(?<!\*)\*(?![*\w])")
_WORD_RE = re.compile(r"[^\W\d_](?:[\w'’-]*[^\W_])?|'[^\W\d_][\w'’-]*")
_ELISION_RE = re.compile(r"^(?:l|d|qu|j|n|s|c|m|t|jusqu|lorsqu|puisqu)['’](?=\w)", re.IGNORECASE)
_PATRONYMIC = {"ben", "bar", "bat", "bené", "bnei"}
_HEB_MARKS_RE = re.compile(rf"[{_MARKS}\u05f3\u05f4\"']")


def check_options(options: dict) -> list[str]:
    problems = []
    min_words = options.get("min_words", DEFAULT_MIN_WORDS)
    if not isinstance(min_words, int) or min_words < 2:
        problems.append(f"'min_words' must be an integer >= 2, got {min_words!r}")
    ignore = options.get("ignore", [])
    if not isinstance(ignore, list) or not all(isinstance(t, str) for t in ignore):
        problems.append("'ignore' must be a list of expressions")
    for key in ("require_first", "strict"):
        if not isinstance(options.get(key, False), bool):
            problems.append(f"'{key}' must be true or false")
    return problems


@lru_cache(maxsize=1)
def _french() -> frozenset[str]:
    from spellchecker import SpellChecker

    return frozenset(SpellChecker(language="fr").word_frequency.dictionary)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def is_french(word: str) -> bool:
    """In the French dictionary (elisions removed; hyphenated: every part is French)."""
    word = _ELISION_RE.sub("", word.replace("’", "'")).strip("'").lower()
    if not word:
        return True
    french = _french()
    return word in french or all(p.strip("'") in french for p in word.split("-") if p.strip("'"))


def _words(text: str) -> list[re.Match]:
    return list(_WORD_RE.finditer(text))


def translit_key(text: str) -> tuple[str, ...]:
    """Normalized words of a transliteration: `ha-Qadosh Baroukh Hou` = `HaQadosh baroukh hou`."""
    words = (_ELISION_RE.sub("", _strip_accents(m.group()).lower()) for m in _words(text.replace("’", "'")))
    return tuple(w for w in (re.sub(r"['-]", "", w) for w in words) if w)


def hebrew_key(text: str) -> tuple[str, ...]:
    text = _HEB_MARKS_RE.sub("", unicodedata.normalize("NFC", text))
    return tuple(re.findall(rf"[{_LETTERS}]+", text))


def _contains(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    n = len(shorter)
    return n > 0 and any(longer[i:i + n] == shorter for i in range(len(longer) - n + 1))


@dataclass
class Expression:
    key: tuple[str, ...]
    script: str  # "translit" | "hebrew"
    text: str  # first occurrence as written
    first: int  # position of the first occurrence
    spans: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, form) of the occurrences
    forms: set[str] = field(default_factory=set)  # full, no_translation, translit, hebrew


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        chars[start:end] = "\n" * (end - start)
    return "".join(chars)


def compute(output: str, *, input_text: str = "", reference: Optional[str] = None,
            options: Optional[dict] = None) -> MetricResult:
    options = options or {}
    min_words = int(options.get("min_words", DEFAULT_MIN_WORDS))
    ignored = {translit_key(t) for t in options.get("ignore", [])}
    require_first = bool(options.get("require_first", False))
    strict = bool(options.get("strict", False))
    translation_after = 0
    text = unicodedata.normalize("NFC", output)
    positions = text == output  # offsets in the output are only meaningful without normalization

    expressions: dict[tuple[str, tuple[str, ...]], Expression] = {}
    full_forms: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []  # (position, translit key, hebrew key)

    def add(script: str, key: tuple[str, ...], written: str, span: tuple[int, int], form: str) -> None:
        if len(key) < min_words or (script == "translit" and key in ignored):
            return
        expression = expressions.setdefault((script, key), Expression(key, script, written.strip(), span[0]))
        if span[0] < expression.first:
            expression.first, expression.text = span[0], written.strip()
        expression.spans.append((*span, form))
        expression.forms.add(form)

    # Hebrew script followed by (transliteration[, translation]).
    covered: list[tuple[int, int]] = []
    annotated_hebrew: list[tuple[str, ...]] = []
    for match in _FULL_RE.finditer(text):
        translit = (match.group("italic") or match.group("plain") or "").strip()
        if re.search(r"\d", translit) or not _words(translit):
            continue
        translation = (match.group("translation") or "").strip(" «»\"“”'")
        complete = bool(re.search(r"\w", translation))
        if not complete and not strict and re.search(r"\w", match.group("after") or ""):
            complete = True
            translation_after += 1
        t_key, h_key = translit_key(translit), hebrew_key(match.group("heb"))
        covered.append(match.span())
        annotated_hebrew.append(h_key)
        if complete:
            full_forms.append((match.start(), t_key, h_key))
        form = "full" if complete else "no_translation"
        if len(t_key) >= min_words:
            add("translit", t_key, translit, match.span(), form)
        else:
            add("hebrew", h_key, f"{match.group('heb')} ({translit})", match.span(), form)

    # Hebrew script alone (not a repetition of an annotated Hebrew form, allowed by rule 3).
    rest = _mask(text, covered)
    for match in _HEB_SPAN_RE.finditer(rest):
        key = hebrew_key(match.group())
        if not any(_contains(h, key) for h in annotated_hebrew):
            add("hebrew", key, match.group(), match.span(), "hebrew")

    # Transliterations in italics, then non-italic runs of non-French words.
    italic_spans = []
    for match in _ITALIC_RE.finditer(rest):
        span_text = match.group("text")
        words = [w.group() for w in _words(span_text)]
        if len(words) < min_words or re.search(r"\d", span_text):
            continue
        foreign = [w for w in words if not is_french(w)]
        if len(foreign) * 2 >= len(words) and not _patronymic(words):
            italic_spans.append(match.span())
            add("translit", translit_key(span_text), span_text, match.span(), "translit")
    plain = _mask(_mask(rest, italic_spans), [m.span() for m in _HEB_SPAN_RE.finditer(rest)])
    pending: list[tuple[tuple[str, ...], str, tuple[int, int]]] = []
    for run in _foreign_runs(plain, min_words):
        words = [w.group() for w in run]
        if _patronymic(words):
            continue
        span = (run[0].start(), run[-1].end())
        written = _ELISION_RE.sub("", plain[span[0]:span[1]].replace("’", "'"))
        key = translit_key(written)
        if all(w.lstrip("'’")[:1].isupper() for w in words):
            pending.append((key, written, span))
        else:
            add("translit", key, written, span, "translit")
    for key, written, span in pending:
        if ("translit", key) in expressions:
            add("translit", key, written, span, "translit")

    rows = []
    for expression in sorted(expressions.values(), key=lambda e: e.first):
        side = 1 if expression.script == "translit" else 2
        containing = [f[0] for f in full_forms if _contains(f[side], expression.key)]
        first_ok = bool(containing) and min(containing) <= expression.first
        compliant = first_ok if require_first else bool(containing)
        if compliant:
            problem = None
        elif "no_translation" in expression.forms:
            problem = "no translation"
        elif expression.script == "hebrew":
            problem = "no transliteration"
        else:
            problem = "no Hebrew"
        row = {"expression": expression.text[:160], "occurrences": len(expression.spans),
               "compliant": compliant, "first_occurrence": first_ok, "problem": problem}
        if positions:
            row["spans"] = [{"start": s, "end": e, "form": f} for s, e, f in sorted(expression.spans)[:SPAN_LIMIT]]
        rows.append(row)

    n = len(rows)
    compliant = [r for r in rows if r["compliant"]]
    problems = [r for r in rows if not r["compliant"]]
    details = {
        "expressions": n,
        "compliant": len(compliant),
        "first_occurrence_rate": sum(r["first_occurrence"] for r in rows) / n if n else None,
        "no_translation": sum(r["problem"] == "no translation" for r in problems),
        "no_hebrew": sum(r["problem"] == "no Hebrew" for r in problems),
        "no_transliteration": sum(r["problem"] == "no transliteration" for r in problems),
        "items": rows[:ITEM_LIMIT],
        "translation_after": translation_after,
        "require_first": require_first,
        "strict": strict,
    }
    for key in ("no_translation", "no_hebrew", "no_transliteration"):
        details[f"{key}_rate"] = details[key] / n if n else None
    return MetricResult(len(compliant) / n if n else None, details)


def _patronymic(words: list[str]) -> bool:
    return any(w.lower() in _PATRONYMIC for w in words[1:-1])


def _foreign_runs(text: str, min_words: int) -> list[list[re.Match]]:
    """Runs of consecutive words (separated by spaces only) not in the French dictionary."""
    runs, current, previous_end = [], [], None
    for match in _words(text):
        gap = text[previous_end:match.start()] if previous_end is not None else ""
        if current and (gap.strip() or "\n" in gap):
            runs.append(current)
            current = []
        if is_french(match.group()):
            if current:
                runs.append(current)
            current = []
        else:
            current.append(match)
        previous_end = match.end()
    if current:
        runs.append(current)
    return [r for r in runs if len(r) >= min_words]


# Report (review app): unit of the value and definition of each detail column.
UNIT = '% of the Hebrew expressions of the output'
DETAIL_DOCS = {
    'expressions': 'Number of distinct Hebrew expressions found in the output (the denominator). Unit: number of expressions.',
    'first_occurrence_rate': 'Share of the expressions written in full form (Hebrew + transliteration + translation) at their first occurrence. Unit: % of the expressions.',
    'no_translation_rate': 'Share of the expressions never given with their translation. Unit: % of the expressions.',
    'no_hebrew_rate': 'Share of the expressions never written in Hebrew script. Unit: % of the expressions.',
    'no_transliteration_rate': 'Share of the expressions never given with a transliteration. Unit: % of the expressions.',
}
