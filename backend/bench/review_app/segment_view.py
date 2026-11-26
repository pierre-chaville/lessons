"""Segment view of a correction in Hebrew script (review app): the differences of each segment as
pieces of text with a category, that the frontend maps to CSS classes.

The categories and the counters come from metrics.hebrew.compare_unit, the function the metrics
use (hebrew_identification, wer_french), so the view and the summary table always agree.

A piece is {"t": text, "c": category, "s": severity, "h": tooltip, "gap": true for a missing
word}; plain text has only "t". Each Hebrew passage (consecutive Hebrew words, without the
punctuation around it) is grouped as {"rtl": [pieces]}, rendered in <bdi dir="rtl">.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bench.metrics.hebrew import (LABELS, SEVERITIES, SEVERITY, Glossary, Token, UnitAnalysis, _alignment_key, blocks,
                                  category_counts, compare_unit, cross_script_matches, doubts, is_hebrew, render,
                                  rendered_key, tokens)

GOLD_DOUBT, GOLD_CHANGED = "gold_doubt", "gold_changed"
SEVERITY_LABELS = {
    "error": "semantic error", "drift": "content drift", "form": "instruction or word form not respected",
    "variant": "harmless variant", "cosmetic": "cosmetic difference",
}
_RTL_JOINER_RE = re.compile("^[\\s,;:.־׃׀]*$")  # text allowed inside a Hebrew passage
_ORDER = {severity: i for i, severity in enumerate(SEVERITIES)}


@dataclass
class Mark:
    category: str
    title: str

    @property
    def severity(self) -> str:
        return SEVERITY.get(self.category, "cosmetic")


@dataclass
class RenderOptions:
    glossary: Glossary
    primary: str = "translit"
    quotations_in_hebrew: bool = True


def legend() -> list[dict]:
    return [{"severity": s, "label": SEVERITY_LABELS[s], "categories": [{"category": c, "label": LABELS[c]} for c in cats]}
            for s, cats in SEVERITIES.items()]


# --------------------------------------------------------------------------- #
# Pieces
# --------------------------------------------------------------------------- #


def _piece(mark: Optional[Mark], text: str, gap: bool = False) -> dict:
    if mark is None:
        return {"t": text}
    piece = {"t": text, "c": mark.category, "s": mark.severity if mark.category != GOLD_DOUBT else "doubt",
             "h": mark.title}
    if gap:
        piece["gap"] = True
    return piece


def pieces(clean: str, words: list[Token], marks: dict[int, Mark], gaps: dict[int, list[Mark]]) -> list[dict]:
    """Pieces of `clean` (the text the token positions refer to): marked words, gaps before the
    word of their index (len(words): at the end), Hebrew passages grouped."""
    flat: list[tuple[str, object]] = []  # ("text", str) | ("word", index) | ("gap", Mark)
    position = 0
    for index, word in enumerate(words):
        if word.start > position:
            flat.append(("text", clean[position:word.start]))
        flat += [("gap", mark) for mark in gaps.get(index, [])]
        flat.append(("word", index))
        position = word.end
    flat += [("gap", mark) for mark in gaps.get(len(words), [])]
    if position < len(clean):
        flat.append(("text", clean[position:]))

    def to_piece(element) -> dict:
        kind, value = element
        if kind == "word":
            word = words[value]
            return _piece(marks.get(value), clean[word.start:word.end])
        if kind == "gap":
            return _piece(value, "‸", gap=True)
        return {"t": value}

    def hebrew_word(element) -> bool:
        return element[0] == "word" and words[element[1]].hebrew

    result: list[dict] = []
    i = 0
    while i < len(flat):
        if not hebrew_word(flat[i]):
            result.append(to_piece(flat[i]))
            i += 1
            continue
        last = k = i
        while k + 1 < len(flat):
            kind, value = flat[k + 1]
            if hebrew_word(flat[k + 1]):
                last = k + 1
            elif not (kind == "gap" or (kind == "text" and _RTL_JOINER_RE.match(value))):
                break
            k += 1
        result.append({"rtl": [to_piece(e) for e in flat[i:last + 1]]})
        i = last + 1
    return result


def worst(marks: list[Mark]) -> Optional[str]:
    severities = [m.severity for m in marks if m.category in SEVERITY]
    return min(severities, key=_ORDER.__getitem__) if severities else None


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #


def _rendering(word: str, options: RenderOptions) -> list[Token]:
    rendered, _ = render([Token(word, is_hebrew(word))], options.glossary, options.primary,
                         options.quotations_in_hebrew)
    return rendered


def _rendering_line(gold: str, output: str, options: RenderOptions) -> str:
    """`'Omer = 'Omer`: how the reader sees both forms."""
    a, b = _rendering(gold, options), _rendering(output, options)
    if all(t.hebrew for t in a + b) and not options.glossary.lookup(gold) and not options.glossary.lookup(output):
        return "rendered: as written (not in the glossary)"
    same =[rendered_key(t) for t in a] == [rendered_key(t) for t in b] or (
        len(a) == len(b) == 1 and cross_script_matches(a, b) == 1)
    return f"rendered: {' '.join(t.text for t in a)} {'=' if same else '≠'} {' '.join(t.text for t in b)}"


def output_marks(unit: UnitAnalysis, options: RenderOptions) -> tuple[dict[int, Mark], dict[int, list[Mark]]]:
    """Marks of the output words and gaps, from the level A terms then the level B edits."""
    marks: dict[int, Mark] = {}
    gaps: dict[int, list[Mark]] = {}
    for term in unit.terms:
        if term.output_index is None:
            gaps.setdefault(term.gap_at, []).append(Mark("missing", f"{LABELS['missing']}: {term.gold}"))
            continue
        category = "exact_niqqud" if term.niqqud_differs else term.category
        if category == "exact":
            continue
        marks[term.output_index] = Mark(category, f"{LABELS[category]}: {term.gold} → {term.output}\n"
                                                  + _rendering_line(term.gold, term.output, options))
    for edit in unit.edits:
        mark = Mark(edit.category, f"{LABELS[edit.category]}: {edit.label}")
        if not edit.output_tokens:
            gaps.setdefault(edit.gap_at, []).append(mark)
        for index in edit.output_tokens:
            marks.setdefault(index, mark)
    for index, gold in unit.french_variants:
        marks.setdefault(index, Mark("french_variant", f"{LABELS['french_variant']}: gold «{gold}»"))
    for index, gold in unit.minor:
        marks.setdefault(index, Mark("minor", f"{LABELS['minor']}: gold «{gold}»"))
    return marks, gaps


def _doubt_title(attributes: dict) -> str:
    lines = ["doubtful in the gold (<d>)"]
    if attributes.get("alt"):
        lines.append("alternatives: " + " | ".join(attributes["alt"].split("|")))
    for key in ("i", "brut"):
        if attributes.get(key):
            lines.append(f"transcription: {attributes[key]}")
    return "\n".join(lines)


def gold_column(gold_raw: str) -> tuple[list[dict], int]:
    """Pieces of the gold segment (its doubt tags marked) and the number of doubt tags."""
    clean, spans = doubts(gold_raw)
    words = tokens(gold_raw)
    marks = {}
    for span in spans:
        for index, word in enumerate(words):
            if word.start >= span.start and word.end <= span.end:
                marks[index] = Mark(GOLD_DOUBT, _doubt_title(span.attributes))
    return pieces(clean, words, marks, {}), len(spans)


def initial_column(initial_raw: str, gold_raw: str) -> tuple[list[dict], int]:
    """Pieces of the raw transcript, the words changed by the gold in gray; number of changes."""
    words, gold = tokens(initial_raw), tokens(gold_raw)
    marks: dict[int, Mark] = {}
    gaps: dict[int, list[Mark]] = {}
    changes = 0
    for equal, g_start, g_end, i_start, i_end in blocks([_alignment_key(t) for t in gold],
                                                         [_alignment_key(t) for t in words]):
        if equal:
            continue
        changes += 1
        target = " ".join(t.text for t in gold[g_start:g_end]) or "∅"
        mark = Mark(GOLD_CHANGED, f"changed in the gold: → {target}")
        if i_start == i_end:
            gaps.setdefault(i_start, []).append(mark)
        for index in range(i_start, i_end):
            marks[index] = mark
    return pieces(doubts(initial_raw)[0], words, marks, gaps), changes


def output_cell(start: int, gold_raw: str, output_raw: str, initial_raw: str, options: RenderOptions,
                case_sensitive: bool, one_letter_variants: bool = True) -> dict:
    unit = compare_unit(start, gold_raw, output_raw, initial_raw, options.glossary, case_sensitive,
                        one_letter_variants)
    marks, gaps = output_marks(unit, options)
    all_marks = list(marks.values()) + [m for ms in gaps.values() for m in ms]
    clean = doubts(output_raw)[0]
    return {"pieces": pieces(clean, unit.output, marks, gaps), "worst": worst(all_marks),
            "counts": category_counts(unit), "text": clean, "raw": output_raw}
