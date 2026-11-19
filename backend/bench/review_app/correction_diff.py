"""Word differences of a corrected segment with corrected.md, by severity (review app, correction)."""

from __future__ import annotations

import html
from typing import Optional

from rapidfuzz.distance import Levenshtein

from bench.metrics.text import WORD_LEVELS, strip_speaker_tag, tokenize

# Severity of a difference, from the least to the most important: "minor" = counted by wer only
# (case, accents, inner apostrophes / hyphens), "norm" = counted by wer_norm but not by wer_fold
# (transliteration variant), "fold" = still counted by wer_fold (real error).
SEVERITIES = ("minor", "norm", "fold")


class Comparator:
    """Compares texts with corrected.md, ignoring punctuation and spacing (case counts by default)."""

    def __init__(self, case_sensitive: bool = True):
        self.lowercase = not case_sensitive

    def words(self, text: str, severity: str = "minor") -> list[str]:
        """Words compared at a severity level: the words of the comparator for "minor", the words of
        wer_norm / wer_fold for "norm" / "fold"."""
        if severity == "minor":
            return tokenize(strip_speaker_tag(text), lowercase=self.lowercase)
        transform = WORD_LEVELS[severity]
        return [w for w in map(transform, tokenize(strip_speaker_tag(text))) if w]

    def same(self, text: str, gold: str) -> bool:
        return self.words(text) == self.words(gold)

    def severity(self, text: str, gold: str) -> Optional[str]:
        """Most important level at which `text` differs from `gold` (None if they are the same)."""
        for severity in reversed(SEVERITIES):
            if self.words(text, severity) != self.words(gold, severity):
                return severity
        return None

    def highlight(self, text: str, gold: str) -> str:
        """HTML of `text` with the words that differ from `gold` in <mark class="severity">, and a
        caret where gold words are missing. Each word gets the most important level at which it differs."""
        raw = text.split()
        marked: dict[int, str] = {}
        gaps: dict[int, str] = {}
        for severity in SEVERITIES:
            units = [(i, " ".join(self.words(w, severity))) for i, w in enumerate(raw)]
            units = [(i, u) for i, u in units if u]  # punctuation-only words are never marked
            for op in Levenshtein.opcodes([u for _, u in units], self.words(gold, severity)):
                if op.tag in ("replace", "delete"):
                    marked.update((units[k][0], severity) for k in range(op.src_start, op.src_end))
                elif op.tag == "insert":
                    gaps[units[op.src_start][0] if op.src_start < len(units) else len(raw)] = severity
        out = []
        for i, w in enumerate([*raw, ""]):
            if i in gaps:
                out.append(f"<mark class='{gaps[i]} gap' title='missing words'>‸</mark>")
            if w:
                out.append(f"<mark class='{marked[i]}'>{html.escape(w)}</mark>" if i in marked else html.escape(w))
        return " ".join(out)
